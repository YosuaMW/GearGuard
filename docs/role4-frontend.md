# Role 4 · Frontend Dashboard

> To agree on: see [integration-checklist.md](integration-checklist.md) item 3.

## API address

| Where | Base URL |
|---|---|
| Anywhere (HTTPS) | `https://yosua.tailf140ab.ts.net` |
| Same Wi-Fi as the Pi | `http://yosua.local:8000` |

Swagger (try every endpoint): `<base URL>/docs`. Keep the base URL in an env var (e.g. `NEXT_PUBLIC_API_URL`).
CORS: `http://localhost:3000` and `https://gearguard-sky.vercel.app` are allowed. **If the dashboard domain changes, tell Yosua** so it can be added to `CORS_ORIGINS`. Every endpoint is **GET**.

Dashboard: **https://gearguard-sky.vercel.app** (the old `siaga-mesin.vercel.app` domain is gone).

## General rules

- Times: ISO 8601 with offset (UTC). Show them in WIB in the UI.
- `anomaly_score` and `score` are on a **0–1** scale (the UI shows ×100, e.g. 0.63 → "63 / 100").
- `availability` is on a **0–1** scale (0.957 → "95.7%").
- Categories come in two forms: `category` = display label (English, show as-is) and `category_id` = stable id for colours/icons.
- `range` parameter: `shift` (default for reports) · `today` (default for lists) · `1h` · `8h` · `24h`. Shifts: 06–14, 14–22, 22–06 WIB.
- Sensor values and scores can be `null` (machine hasn't sent data yet / baseline not computed yet).

| `category_id` | `category` |
|---|---|
| `material` | Waiting for material |
| `mechanical` | Breakdown – Mechanical |
| `electrical` | Breakdown – Electrical |
| `overheat` | Breakdown – Overheat |
| `changeover` | Changeover / setup |
| `break` | Break / scheduled (does not reduce availability) |
| `other` | Other |
| `review` | Needs review (AI confidence < 0.6) |

Machines: `m1` Conveyor motor (live rig) · `m2` Pump · `m3` Mixer · `m4` Compressor (replay).

## Dashboard page → endpoint map

| Dashboard section | Endpoint | Polling |
|---|---|---|
| Overview: line diagram + machine cards | `/machines` | 1 s |
| Overview: KPI (availability, downtime, active alerts, stops without reason) + badge "Simulated data" | `/summary` | 5 s |
| Machine card "Vibration, last 2 min" & Machines page charts | `/telemetry?minutes=2` | 2–5 s |
| "Alert limit" line on charts | `baseline.<sensor>.limit_high` from `/machines` | with `/machines` |
| Predictive alerts / alert box on Machines | `/alerts?active=true` | 2 s |
| Today on the line / Stops and operator answers | `/events` (+ `/alerts` for "anomaly alert raised") | 2 s |
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
- `status`: `running` / `anomaly` / `stopped`. A machine that sends no data for 30 s is reported as `stopped` (with `online: false` and `stopped_since` = time of its last data), so no extra "offline" state is needed.
- `awaiting_reason`: the bot asked and the operator hasn't answered yet → "waiting for reply" marker.
- `baseline.limit_high` = the level that triggers an alert (normal + 3 × spread). `null` until the baseline is computed.
- `GET /machines/{id}` = one machine, same shape.

## `GET /telemetry?minutes=2&machine_id=m2`

```json
{"bucket_seconds": 1.0,
 "series": {"m2": [{"ts": "2026-10-14T12:05:03+00:00", "current_a": 2.31, "vib_rms": 0.401, "temp_c": 45.7}]}}
```
- Without `machine_id` → all machines. `minutes` 0–60. At most ~120 points per machine (averaged per `bucket_seconds`).

## `GET /summary?range=shift`

```json
{"window": {"range": "shift", "label": "Shift 2 · 14:00–22:00", "start": "...", "end": "...", "shift_end": "..."},
 "availability": 0.957, "downtime_minutes": 83.0, "stops": 9,
 "active_alerts": 0, "stops_without_reason": 1,
 "data_mode": "replay", "ai_mode": "mock"}
```
- `data_mode`: `live` (a live machine is online) · `replay` (simulator only) · `offline`. Drives the "Simulated data" badge.
- `ai_mode`: `mock` (AMD not connected yet) or `amd`.

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
- Newest first. `ongoing: true` = the machine is still stopped.
- `answer_type`: `voice` / `text` (operator) · `replay` (reason from the simulator) · `null` (no answer yet).
- One event can be shown as two timeline rows: "stopped for 18 min" (`start_ts`, `duration_s`) and "reason: …" (`category`, `transcript`).

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
- `active=true` → only alerts still active (no time limit). Default: active ones + any raised within `range`.
- `explanation_source`: `rules` (now) → `ai` once role 3's `/explain` is connected. Then `sources` contains `[{"title": "Centrifugal pump manual", "page": 42, "snippet": "..."}]` for the "Check: …" line.
- Older alerts may have `now`/`normal`/`pct` = `null`.

## `GET /pareto?range=shift&machine_id=`

```json
{"window": {...}, "total_minutes": 90.0, "unexplained_minutes": 2.5,
 "categories": [
   {"category_id": "material", "category": "Waiting for material", "minutes": 39.0, "stops": 3, "pct": 43.3, "cumulative_pct": 43.3}
 ]}
```
- Already sorted largest first. `unexplained_minutes` = stops with no reason yet (not included in `categories`).

## `GET /availability?range=shift`

```json
{"window": {...}, "line_availability": 0.953,
 "machines": [{"machine_id": "m1", "machine_name": "Conveyor motor", "availability": 0.95,
               "run_minutes": 412.0, "downtime_minutes": 21.5, "planned_stop_minutes": 15.0}]}
```
- Availability = run time ÷ (run time + unplanned stops). Offline time and scheduled breaks are excluded.

## `GET /ai-usage`

```json
{"mode": "mock", "since": "2026-10-14T00:00:00+07:00",
 "endpoints": [{"endpoint": "/transcribe", "description": "Voice note to text", "model": "whisper-large-v3",
                "calls_today": 12, "success_rate": 1.0, "avg_latency_ms": 820,
                "prompt_tokens": null, "completion_tokens": null, "mock": false, "last_call": "..."}]}
```
- Live now: `/transcribe` runs **Whisper on the Raspberry Pi** (model `faster-whisper-base-pi`); `/classify` and `/explain` run **Qwen3.8-27B on AMD Token Factory**. Please say this on the page (e.g. *"Speech-to-text runs on the edge gateway; classification and explanations run on AMD."*) so the page title doesn't overclaim.
- `/explain` latency is ~30–50 s: the model reasons before answering. Alerts in `/alerts` get `explanation_source: "ai"` once it arrives; until then the rule-based text is shown.
- Always 3 rows: `/transcribe`, `/classify`, `/explain`. While `mode = mock`, `model` is `mock` / `keyword-rules`; show "To be confirmed by role 3" when `mock = true` or `calls_today = 0`.
