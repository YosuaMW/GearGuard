# Role 1 · Hardware & Anomaly Model

How to connect the ESP32 and sensors to the SiagaMesin backend on the Raspberry Pi.

> To agree on: see [integration-checklist.md](integration-checklist.md) items 4–5 (both optional).

## 1. Network

- **The ESP32 and the Raspberry Pi must be on the same Wi-Fi network.** MQTT is not exposed to the internet.
- Avoid campus/public Wi-Fi (captive portals and client isolation block device-to-device traffic). Safest: a **phone hotspot** or a dedicated team router.
- Broker: **`yosua.local`**, port **1883**, no username/password for now.
- The Pi's IP can change. Resolve `yosua.local` with **ESPmDNS** instead of hardcoding an IP. Fallback: check the IP on the Pi with `hostname -I`.

## 2. MQTT message format

**Topic:** `siagamesin/<machine_id>/telemetry` (live rig = `m1`)
**Rate:** 1 message per second

```json
{
  "machine_id": "m1",
  "name": "Conveyor motor",
  "source": "live",
  "ts": "2026-10-14T14:02:00Z",
  "current_a": 1.8,
  "vib_rms": 0.42,
  "temp_c": 41.5
}
```

| Field | Required | Notes |
|---|---|---|
| `machine_id` | ✅ | `m1` for the live rig |
| `current_a` | ✅ | Motor current (A), from the PZEM-004T |
| `vib_rms` | ✅ | **Vibration RMS over 1 second**, not raw samples. Compute it on the ESP32 from hundreds of accelerometer samples |
| `temp_c` | ✅ | Motor body temperature (°C), from the DS18B20 |
| `ts` | optional | ISO 8601 UTC. If omitted, the backend uses the Pi's clock (recommended unless the ESP32 is NTP-synced) |
| `name`, `source` | optional | `source` defaults to `live` |

**Stop detection:** the backend treats the machine as stopped when `current_a < 0.3` A for ≥ 5 seconds. If your rig's idle current differs, tell Yosua so the threshold (`STOP_CURRENT_A` in `.env`) can be changed.

Need extra features for the model (e.g. `vib_peak`, FFT bands)? Add the fields to the JSON and tell Yosua so database columns can be added.

## 3. Connecting the ESP32 to the backend

```
ESP32 (sensors) ──Wi-Fi──► MQTT broker on the Pi (yosua.local:1883)
                                 │
                            worker → database → API / dashboard / Telegram bot
```

The ESP32 only needs to join the **same Wi-Fi as the Pi** and publish one JSON message per second to `siagamesin/m1/telemetry`. Everything after that (storing, stop detection, anomaly detection, Telegram questions, dashboard) is handled by the backend.

**Recommended wiring (ESP32 DevKit V1)**

| Sensor | Pins | Notes |
|---|---|---|
| PZEM-004T v3 (current) | TX → GPIO16 (RX2), RX → GPIO17 (TX2), 5 V → VIN, GND | CT clamp around **one** wire (live) of the fan's power cable; 220 V wiring stays inside the closed box with the MCB |
| MPU6050 (vibration) | SDA → GPIO21, SCL → GPIO22, VCC → 3V3, GND | Mount it firmly on the motor body (bolt or strong double tape) |
| DS18B20 (temperature) | DATA → GPIO4 + 4.7 kΩ pull-up to 3V3, VCC → 3V3, GND | Taped to the motor housing |

Arduino libraries: `PubSubClient`, `PZEM004Tv30`, `Adafruit MPU6050` (+ `Adafruit Unified Sensor`), `OneWire`, `DallasTemperature`. `WiFi` and `ESPmDNS` are built into the ESP32 core. Board: **ESP32 Dev Module**.

**Vibration RMS:** sample the accelerometer ~400 times over 1 second, subtract the average of each axis (removes gravity and offset), take the RMS of what remains, and convert m/s² to g (÷ 9.80665). Send that single number as `vib_rms`.

**Connection checklist**
1. On the Pi, watch incoming MQTT: `docker compose exec mqtt mosquitto_sub -t "siagamesin/#" -v`
2. First flash a sketch that sends **fixed fake values** (the minimal example in 3b with constants instead of sensor reads). The Serial Monitor (115200) should show Wi-Fi connected, the broker IP found, MQTT connected, then one message per second.
3. The Pi terminal from step 1 shows `siagamesin/m1/telemetry {...}` every second.
4. `/status` on Telegram or `GET /machines` shows **Conveyor motor** running and online.
5. Switch to real sensor reads. Every message should contain all three fields. If a sensor fails, **leave its field out** rather than sending 0; a missing or zero current is read as "stopped".
6. Run the rig normally for 15–30 min, then recompute the baseline (section 4).

**If the ESP32 can't find the broker:** it can't resolve `yosua.local` on that network. Use the Pi's IP instead (`hostname -I` on the Pi) and remember it changes if the Pi moves to another Wi-Fi.

## 3b. Minimal ESP32 example (Arduino)

Libraries: `PubSubClient`, `ESPmDNS` (built into the ESP32 core).

```cpp
#include <WiFi.h>
#include <ESPmDNS.h>
#include <PubSubClient.h>

const char* SSID = "HOTSPOT_NAME";
const char* PASS = "HOTSPOT_PASSWORD";

WiFiClient net;
PubSubClient mqtt(net);
IPAddress brokerIP;

void connectMqtt() {
  while (!mqtt.connected()) {
    if (brokerIP == IPAddress()) brokerIP = MDNS.queryHost("yosua");  // yosua.local
    mqtt.setServer(brokerIP, 1883);
    if (!mqtt.connect("esp32-m1")) { brokerIP = IPAddress(); delay(2000); }
  }
}

void setup() {
  WiFi.begin(SSID, PASS);
  while (WiFi.status() != WL_CONNECTED) delay(500);
  MDNS.begin("esp32-m1");
  connectMqtt();
}

void loop() {
  if (!mqtt.connected()) connectMqtt();
  mqtt.loop();

  float current = readCurrent();   // PZEM-004T
  float vibRms  = readVibRms();    // RMS of accelerometer samples over ~1 s
  float temp    = readTemp();      // DS18B20

  char buf[160];
  snprintf(buf, sizeof(buf),
    "{\"machine_id\":\"m1\",\"source\":\"live\",\"current_a\":%.2f,\"vib_rms\":%.3f,\"temp_c\":%.1f}",
    current, vibRms, temp);
  mqtt.publish("siagamesin/m1/telemetry", buf);
}
```

`readVibRms()` should block for about 1 second while sampling, so the loop naturally runs at 1 Hz.

**Test without an ESP32** (from a laptop or the Pi on the same network):
```
mosquitto_pub -h yosua.local -t siagamesin/m1/telemetry -m '{"machine_id":"m1","current_a":1.8,"vib_rms":0.42,"temp_c":41.5}'
```
Then send `/status` to the Telegram bot, or open `/machines` on the API.

## 4. Once the rig is connected: calibrate the baseline

Anomaly detection compares live data with each machine's normal condition. The `m1` baseline currently comes from simulated data, so:

1. Run the rig **normally** (no disturbances) for **15–30 minutes**.
2. Ask Yosua to run `docker compose exec worker python /app/tools/baseline.py --minutes 30` on the Pi.

Without this step, real data will be flagged as anomalous right away.

## 5. `/score` contract (autoencoder)

The backend currently uses a z-score fallback. When the autoencoder is ready, provide:

**`POST /score`**
```json
{
  "machine_id": "m1",
  "window": [
    {"ts": "2026-10-14T14:02:00Z", "current_a": 1.8, "vib_rms": 0.42, "temp_c": 41.5}
  ]
}
```
`window` = the last 60 samples (60 seconds), oldest first.

**Response**
```json
{"score": 0.73, "anomaly": true, "threshold": 0.5}
```
- `score`: 0–1 (0 = normal). The dashboard and bot already use this scale.
- Target latency < 1 s. If the endpoint is down or slow, the backend falls back to z-score.

## 6. Recording data for replay

CSV format used by the replay simulator:
```
ts,machine_id,current_a,vib_rms,temp_c
2026-10-14T14:02:00Z,m1,1.80,0.420,41.5
```
Record 30–60 minutes of normal operation, plus 3 kinds of disturbance (e.g. an unbalanced weight on a fan blade, blocked airflow, motor held back). Note the start and end time of each disturbance.

Rig data already in the database can be exported by Yosua:
```
docker compose exec -T db psql -U siaga -d siagamesin -c "\copy (SELECT ts,machine_id,current_a,vib_rms,temp_c FROM telemetry WHERE machine_id='m1' ORDER BY ts) TO STDOUT CSV HEADER" > m1.csv
```
