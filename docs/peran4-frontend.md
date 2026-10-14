# Peran 4 · Frontend Dashboard

> Yang perlu disepakati: lihat [checklist-integrasi.md](checklist-integrasi.md) poin 3.

## Alamat API

| Kondisi | Base URL |
|---|---|
| Dari mana saja (HTTPS) | `https://yosua.tailf140ab.ts.net` |
| Satu WiFi dengan Raspi | `http://yosua.local:8000` |

Swagger (coba semua endpoint): `<base URL>/docs`. Simpan base URL di env (mis. `NEXT_PUBLIC_API_URL`).
CORS: `http://localhost:3000` sudah diizinkan. **Kirim URL Vercel** supaya ditambahkan. Semua endpoint **GET**.

## Aturan umum

- Waktu: ISO 8601 dengan zona (UTC). Tampilkan dalam WIB di UI.
- `anomaly_score` dan `score` skala **0–1** (UI menampilkan ×100, mis. 0.63 → "63 / 100").
- `availability` skala **0–1** (0.957 → "95.7%").
- Kategori dikirim dua bentuk: `category` = label tampilan (bahasa Inggris, langsung tampilkan) dan `category_id` = id stabil untuk warna/ikon.
- Parameter `range`: `shift` (default untuk laporan) · `today` (default untuk daftar) · `1h` · `8h` · `24h`. Shift: 06–14, 14–22, 22–06 WIB.
- Angka sensor/skor bisa `null` (mesin belum kirim data / baseline belum dihitung).

| `category_id` | `category` |
|---|---|
| `material` | Waiting for material |
| `mechanical` | Breakdown – Mechanical |
| `electrical` | Breakdown – Electrical |
| `overheat` | Breakdown – Overheat |
| `changeover` | Changeover / setup |
| `break` | Break / scheduled (tidak mengurangi availability) |
| `other` | Other |
| `review` | Needs review (confidence AI < 0.6) |

Mesin: `m1` Conveyor motor (live rig) · `m2` Pump · `m3` Mixer · `m4` Compressor (replay).

## Peta halaman → endpoint

| Bagian dashboard | Endpoint | Polling |
|---|---|---|
| Overview: diagram line + kartu mesin | `/machines` | 1 s |
| Overview: KPI (availability, downtime, active alerts, stops without reason) + badge "Simulated data" | `/summary` | 5 s |
| Kartu mesin "Vibration, last 2 min" & grafik di halaman Machines | `/telemetry?minutes=2` | 2–5 s |
| Garis "Alert limit" di grafik | `baseline.<sensor>.limit_high` dari `/machines` | ikut `/machines` |
| Predictive alerts / kotak alert di Machines | `/alerts?active=true` | 2 s |
| Today on the line / Stops and operator answers | `/events` (+ `/alerts` untuk "anomaly alert raised") | 2 s |
| Reports: Where the time went | `/pareto` | 10 s |
| Reports: Availability by machine | `/availability` | 10 s |
| Running on AMD | `/ai-usage` | 10 s |

---

## `GET /machines`

```json
[{
  "id": "m2", "name": "Pump", "source": "replay",
  "status": "anomaly", "online": true,
  "anomaly_score": 0.63,
  "awaiting_reason": false,
  "stopped_since": null,
  "last": {"machine_id": "m2", "ts": "2026-10-14T12:05:59+00:00", "current_a": 2.29, "vib_rms": 0.62, "temp_c": 50.9},
  "baseline": {
    "vib_rms":   {"normal": 0.40, "limit_high": 0.55, "limit_low": 0.25},
    "current_a": {"normal": 2.30, "limit_high": 2.51, "limit_low": 2.09},
    "temp_c":    {"normal": 45.3, "limit_high": 48.0, "limit_low": 42.6}
  }
}]
```
- `status`: `running` / `anomaly` / `stopped`. `online` = ada data ≤ 30 detik terakhir (kalau `false`, tampilkan "Offline").
- `awaiting_reason`: bot sudah bertanya, operator belum menjawab → tanda "waiting for reply".
- `baseline.limit_high` = batas yang memicu alert (normal + 3 × sebaran). `null` kalau baseline belum dihitung.
- `GET /machines/{id}` = satu mesin dengan bentuk sama.

## `GET /telemetry?minutes=2&machine_id=m2`

```json
{"bucket_seconds": 1.0,
 "series": {"m2": [{"ts": "2026-10-14T12:05:03+00:00", "current_a": 2.31, "vib_rms": 0.401, "temp_c": 45.7}]}}
```
- Tanpa `machine_id` → semua mesin. `minutes` 0–60. Maksimal ±120 titik per mesin (dirata-rata per `bucket_seconds`).

## `GET /summary?range=shift`

```json
{"window": {"range": "shift", "label": "Shift 2 · 14:00–22:00", "start": "...", "end": "...", "shift_end": "..."},
 "availability": 0.957, "downtime_minutes": 83.0, "stops": 9,
 "active_alerts": 0, "stops_without_reason": 1,
 "data_mode": "replay", "ai_mode": "mock"}
```
- `data_mode`: `live` (ada mesin live online) · `replay` (hanya simulator) · `offline`. Untuk badge "Simulated data".
- `ai_mode`: `mock` (AMD belum tersambung) atau `amd`.

## `GET /events?range=today&machine_id=m1&limit=50`

```json
[{
  "id": 41, "machine_id": "m1", "machine_name": "Conveyor motor", "source": "live",
  "start_ts": "...", "end_ts": "...", "ongoing": false, "duration_s": 1080,
  "category_id": "material", "category": "Waiting for material", "confidence": 0.93,
  "needs_review": false, "has_reason": true, "awaiting_reason": false,
  "answer_type": "voice", "transcript": "bahan dari gudang belum datang"
}]
```
- Urut terbaru dulu. `ongoing: true` = mesin masih berhenti.
- `answer_type`: `voice` / `text` (operator) · `replay` (alasan dari simulator) · `null` (belum ada jawaban).
- Satu event bisa ditampilkan sebagai dua baris timeline: "stopped for 18 min" (`start_ts`, `duration_s`) dan "reason: …" (`category`, `transcript`).

## `GET /alerts?active=true&machine_id=m2&range=today`

```json
[{
  "id": 7, "machine_id": "m2", "machine_name": "Pump", "source": "replay",
  "ts": "...", "resolved_ts": null, "active": true, "score": 0.63,
  "title": "Vibration rising above normal",
  "explanation": "Vibration is above its normal level, a typical sign of bearing wear...",
  "explanation_source": "rules",
  "sources": [],
  "features": {
    "vib_rms": {"label": "Vibration", "unit": "g RMS", "now": 0.62, "normal": 0.40, "z": 4.1, "pct": 55.0},
    "temp_c":  {"label": "Temperature", "unit": "°C", "now": 50.9, "normal": 45.3, "z": 3.2, "pct": 12.4}
  }
}]
```
- `active=true` → hanya yang masih aktif (tanpa batas waktu). Default: aktif + yang terjadi dalam `range`.
- `explanation_source`: `rules` (sekarang) → `ai` setelah `/explain` dari peran 3 tersambung. Saat itu `sources` berisi `[{"title": "Centrifugal pump manual", "page": 42, "snippet": "..."}]` untuk baris "Check: …".
- Alert lama bisa punya `now`/`normal`/`pct` = `null`.

## `GET /pareto?range=shift&machine_id=`

```json
{"window": {...}, "total_minutes": 90.0, "unexplained_minutes": 2.5,
 "categories": [
   {"category_id": "material", "category": "Waiting for material", "minutes": 39.0, "stops": 3, "pct": 43.3, "cumulative_pct": 43.3}
 ]}
```
- Sudah urut terbesar. `unexplained_minutes` = berhenti yang belum ada alasannya (tidak masuk `categories`).

## `GET /availability?range=shift`

```json
{"window": {...}, "line_availability": 0.953,
 "machines": [{"machine_id": "m1", "machine_name": "Conveyor motor", "availability": 0.95,
               "run_minutes": 412.0, "downtime_minutes": 21.5, "planned_stop_minutes": 15.0}]}
```
- Availability = waktu jalan ÷ (waktu jalan + berhenti tak terencana). Waktu offline dan istirahat terjadwal tidak dihitung.

## `GET /ai-usage`

```json
{"mode": "mock", "since": "2026-10-14T00:00:00+07:00",
 "endpoints": [{"endpoint": "/transcribe", "description": "Voice note to text", "model": "whisper-large-v3",
                "calls_today": 12, "success_rate": 1.0, "avg_latency_ms": 820,
                "prompt_tokens": null, "completion_tokens": null, "mock": false, "last_call": "..."}]}
```
- Selalu 3 baris: `/transcribe`, `/classify`, `/explain`. Selama `mode = mock`, `model` berisi `mock` / `keyword-rules`; tampilkan "To be confirmed by role 3" kalau `mock = true` atau `calls_today = 0`.
