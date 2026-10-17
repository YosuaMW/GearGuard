# Role 1 · Hardware & Anomaly Model

How to connect the ESP32 and sensors to the GearGuard backend on the Raspberry Pi.

> To agree on: see [integration-checklist.md](integration-checklist.md) items 4–5 (both optional).

## 1. Network

The broker can be reached two ways. **Option A is recommended**: it works from any network.

| | Option A: Internet (recommended) | Option B: Same Wi-Fi as the Pi |
|---|---|---|
| Host | `yosua.tailf140ab.ts.net` | `yosua.local` (or the Pi's IP) |
| Port | `8443` (TLS) | `1883` (plain) |
| Arduino client | `WiFiClientSecure` + `setInsecure()` | `WiFiClient` |
| Works on | any Wi-Fi: phone hotspot, campus, home | only the Pi's network, without client isolation |

- **Login is required on both:** username `siaga`, password from Yosua (shared privately; never put it in the repo).
- Option A goes through Tailscale Funnel, which handles TLS, so traffic and password are encrypted.
- Option B: the Pi's IP can change, so resolve `yosua.local` with **ESPmDNS**. Campus/public Wi-Fi usually blocks device-to-device traffic, so use Option A there.

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
| `current_a` | ✅ | Motor current (A), from the SCT-013 clamp |
| `vib_rms` | ✅ | **Vibration RMS over 1 second**, not raw samples. Compute it on the ESP32 from hundreds of accelerometer samples |
| `temp_c` | ✅ | Motor body temperature (°C), from the LM35 |
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

**Wiring (ESP32 DevKit V1)**

| Sensor | Pins | Notes |
|---|---|---|
| SCT-013 (current) | Clamp output → bias circuit → **GPIO35** | Non-invasive clamp around **one** wire (live) of the motor's power cable; no 220 V wiring to the ESP32. Bias the output to mid-supply with two 10 kΩ resistors (3V3–GND) and a 10 µF capacitor. The SCT-013-000 (current output) also needs a burden resistor (~33 Ω); the -030/-050 types have one built in |
| MPU6050 (vibration) | SDA → GPIO21, SCL → GPIO22, VCC → 3V3, GND | Mount it firmly on the motor body (bolt or strong double tape) |
| LM35 (temperature) | VCC → VIN (5 V), OUT → **GPIO34**, GND | Taped to the motor housing. Needs ≥ 4 V supply; output is only ~10 mV/°C so it is safe for the ESP32 ADC |

Arduino libraries: `PubSubClient`, `EmonLib` (current RMS from the SCT-013), `Adafruit MPU6050` (+ `Adafruit Unified Sensor`). `WiFi`, `WiFiClientSecure` and `ESPmDNS` are built into the ESP32 core. Board: **ESP32 Dev Module**.

**Vibration RMS:** sample the accelerometer ~400 times over 1 second, subtract the average of each axis (removes gravity and offset), take the RMS of what remains, and convert m/s² to g (÷ 9.80665). Send that single number as `vib_rms`.

**Temperature (LM35):** connect OUT to an **ADC1 pin (GPIO32–39)**; ADC2 pins can't be read while Wi-Fi is on. Average a few calibrated readings: °C = millivolts ÷ 10. If readings jump around with long wires, add a 0.1 µF capacitor between OUT and GND near the sensor.
```cpp
float readTemp() {
  uint32_t mv = 0;
  for (int i = 0; i < 32; i++) mv += analogReadMilliVolts(34);
  return (mv / 32.0) / 10.0;   // 10 mV = 1 °C
}
```

**Connection checklist**
1. On the Pi, watch incoming MQTT: `source .env && docker compose exec mqtt mosquitto_sub -u siaga -P "$MQTT_PASSWORD" -t "siagamesin/#" -v`
2. First flash a sketch that sends **fixed fake values** (the minimal example in 3b with constants instead of sensor reads). The Serial Monitor (115200) should show Wi-Fi connected, MQTT connected, then one message per second.
3. The Pi terminal from step 1 shows `siagamesin/m1/telemetry {...}` every second.
4. `/status` on Telegram or `GET /machines` shows **Conveyor motor** running and online.
5. Switch to real sensor reads. Every message should contain all three fields. If a sensor fails, **leave its field out** rather than sending 0; a missing or zero current is read as "stopped".
6. Run the rig normally for 15–30 min, then recompute the baseline (section 4).

**If MQTT won't connect**, check `rc` in the Serial Monitor:

| `rc` | Meaning | Fix |
|---|---|---|
| `5` | Not authorised | Wrong username/password |
| `-2` | Connection failed | Wrong host/port, no internet, or (Option A) `WiFiClientSecure` / `setInsecure()` missing. Option B: `yosua.local` not resolved, use the Pi's IP (`hostname -I`) |

## 3b. Minimal ESP32 example (Arduino, Option A)

```cpp
#include <WiFi.h>
#include <WiFiClientSecure.h>
#include <PubSubClient.h>

const char* SSID      = "WIFI_NAME";
const char* PASS      = "WIFI_PASSWORD";
const char* MQTT_HOST = "yosua.tailf140ab.ts.net";
const int   MQTT_PORT = 8443;
const char* MQTT_USER = "siaga";
const char* MQTT_PASS = "ASK_YOSUA";

WiFiClientSecure net;
PubSubClient mqtt(net);

void connectMqtt() {
  while (!mqtt.connected()) {
    if (!mqtt.connect("esp32-m1", MQTT_USER, MQTT_PASS)) {
      Serial.printf("MQTT failed, rc=%d\n", mqtt.state());   // 5 = wrong login, -2 = network
      delay(2000);
    }
  }
  Serial.println("MQTT connected");
}

void setup() {
  Serial.begin(115200);
  WiFi.begin(SSID, PASS);
  while (WiFi.status() != WL_CONNECTED) delay(500);
  Serial.println("Wi-Fi connected");
  net.setInsecure();               // traffic is still encrypted; the certificate is not checked
  mqtt.setServer(MQTT_HOST, MQTT_PORT);
  connectMqtt();
}

void loop() {
  if (!mqtt.connected()) connectMqtt();
  mqtt.loop();

  float current = readCurrent();   // SCT-013 via EmonLib (calcIrms)
  float vibRms  = readVibRms();    // RMS of accelerometer samples over ~1 s
  float temp    = readTemp();      // LM35

  char buf[160];
  snprintf(buf, sizeof(buf),
    "{\"machine_id\":\"m1\",\"source\":\"live\",\"current_a\":%.2f,\"vib_rms\":%.3f,\"temp_c\":%.1f}",
    current, vibRms, temp);
  mqtt.publish("siagamesin/m1/telemetry", buf);
}
```

`readVibRms()` should block for about 1 second while sampling, so the loop naturally runs at 1 Hz.

**Option B (same Wi-Fi):** use `WiFiClient net;` instead of `WiFiClientSecure`, drop `setInsecure()`, and connect to `yosua.local` port `1883` (resolve it with `MDNS.queryHost("yosua")` from `ESPmDNS`, or use the Pi's IP).

**Test without an ESP32**
- From a phone: an MQTT app (e.g. MyMQTT, IoT MQTT Panel, MQTTool) with host `yosua.tailf140ab.ts.net`, port `8443`, **SSL/TLS on**, username/password. Subscribe to `siagamesin/#` and publish to `siagamesin/test/hp` (the `test` topic is ignored by the backend).
- From a laptop with `mosquitto-clients`:
```
mosquitto_pub -h yosua.tailf140ab.ts.net -p 8443 --capath /etc/ssl/certs -u siaga -P <password> -t siagamesin/m1/telemetry -m '{"machine_id":"m1","current_a":1.8,"vib_rms":0.42,"temp_c":41.5}'
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
