# Peran 1 · Hardware & Model Anomali

Panduan menghubungkan ESP32 + sensor ke backend SiagaMesin di Raspberry Pi.

> Yang perlu disepakati: lihat [checklist-integrasi.md](checklist-integrasi.md) poin 4–5 (keduanya opsional).

## 1. Jaringan

- **ESP32 dan Raspi wajib satu jaringan WiFi.** MQTT tidak dibuka ke internet.
- Hindari WiFi kampus/publik (captive portal & client isolation memblokir komunikasi antar perangkat). Paling aman: **hotspot HP** atau router khusus tim.
- Broker: **`yosua.local`**, port **1883**, tanpa username/password (sementara; akan dikunci sebelum demo).
- IP Raspi bisa berubah. Resolve `yosua.local` pakai **ESPmDNS**, jangan hardcode IP. Cadangan: cek IP di Raspi dengan `hostname -I`.

## 2. Format pesan MQTT

**Topic:** `siagamesin/<machine_id>/telemetry` (rig asli = `m1`)
**Frekuensi:** 1 pesan per detik

```json
{
  "machine_id": "m1",
  "name": "Motor Demo 1",
  "source": "live",
  "ts": "2026-10-14T14:02:00Z",
  "current_a": 1.8,
  "vib_rms": 0.42,
  "temp_c": 41.5
}
```

| Field | Wajib | Keterangan |
|---|---|---|
| `machine_id` | ✅ | `m1` untuk rig asli |
| `current_a` | ✅ | Arus motor (A), dari PZEM-004T |
| `vib_rms` | ✅ | **RMS getaran per 1 detik**, bukan sampel mentah. Hitung di ESP32 dari ratusan sampel akselerometer |
| `temp_c` | ✅ | Suhu body motor (°C), dari DS18B20 |
| `ts` | opsional | ISO 8601 UTC. Kalau kosong, backend memakai jam Raspi (disarankan dikosongkan kalau ESP32 belum sinkron NTP) |
| `name`, `source` | opsional | Default `source` = `live` |

**Deteksi berhenti:** backend menganggap mesin berhenti kalau `current_a < 0.3` A selama ≥ 5 detik. Kalau arus idle rig kamu berbeda, kabari Yosua supaya ambangnya diubah (`STOP_CURRENT_A` di `.env`).

Butuh fitur tambahan untuk model (mis. `vib_peak`, pita FFT)? Tambahkan saja field di JSON dan kabari Yosua supaya kolom database ditambah.

## 3. Contoh kode ESP32 (Arduino)

Library: `PubSubClient`, `ESPmDNS` (bawaan ESP32).

```cpp
#include <WiFi.h>
#include <ESPmDNS.h>
#include <PubSubClient.h>

const char* SSID = "NAMA_HOTSPOT";
const char* PASS = "PASSWORD_HOTSPOT";

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
  float vibRms  = readVibRms();    // RMS dari sampel akselerometer selama ~1 detik
  float temp    = readTemp();      // DS18B20

  char buf[160];
  snprintf(buf, sizeof(buf),
    "{\"machine_id\":\"m1\",\"source\":\"live\",\"current_a\":%.2f,\"vib_rms\":%.3f,\"temp_c\":%.1f}",
    current, vibRms, temp);
  mqtt.publish("siagamesin/m1/telemetry", buf);
}
```

`readVibRms()` sebaiknya memblokir ±1 detik sambil mengambil sampel, jadi loop otomatis berjalan 1 Hz.

**Tes tanpa ESP32** (dari laptop/Raspi yang satu jaringan):
```
mosquitto_pub -h yosua.local -t siagamesin/m1/telemetry -m '{"machine_id":"m1","current_a":1.8,"vib_rms":0.42,"temp_c":41.5}'
```
Lalu ketik `/status` di bot Telegram, atau buka `/machines` di API.

## 4. Setelah rig terpasang: kalibrasi baseline

Deteksi anomali membandingkan data dengan kondisi normal tiap mesin. Baseline `m1` sekarang masih dari simulasi, jadi:

1. Jalankan rig **normal** (tanpa gangguan) selama **15–30 menit**.
2. Minta Yosua menjalankan `python tools/baseline.py --minutes 30` di Raspi.

Tanpa langkah ini, data asli akan langsung dianggap anomali.

## 5. Kontrak `/score` (autoencoder)

Backend saat ini memakai deteksi cadangan berbasis z-score. Kalau autoencoder sudah siap, sediakan endpoint:

**`POST /score`**
```json
{
  "machine_id": "m1",
  "window": [
    {"ts": "2026-10-14T14:02:00Z", "current_a": 1.8, "vib_rms": 0.42, "temp_c": 41.5}
  ]
}
```
`window` = 60 data terakhir (60 detik), urut dari lama ke baru.

**Respons**
```json
{"score": 0.73, "anomaly": true, "threshold": 0.5}
```
- `score`: 0–1 (0 = normal). Dashboard dan bot sudah memakai skala ini.
- Target latensi < 1 detik. Kalau endpoint mati atau lambat, backend otomatis kembali ke z-score.

## 6. Rekaman data untuk replay

Format CSV yang dipakai simulator replay:
```
ts,machine_id,current_a,vib_rms,temp_c
2026-10-14T14:02:00Z,m1,1.80,0.420,41.5
```
Rekam: data normal 30–60 menit, plus 3 jenis gangguan (mis. baling-baling diberi beban tidak seimbang, aliran udara dihalangi, motor ditahan). Catat jam mulai–selesai tiap gangguan.

Data dari rig yang sudah masuk database juga bisa langsung diekspor oleh Yosua:
```
psql "$DATABASE_URL" -c "\copy (SELECT ts,machine_id,current_a,vib_rms,temp_c FROM telemetry WHERE machine_id='m1' ORDER BY ts) TO 'm1.csv' CSV HEADER"
```
