# Role 3 · AI Engineer (LLM & Speech on AMD)

Contract between the Raspberry Pi backend and the AI endpoints on AMD Developer Cloud.

> To agree on: see [integration-checklist.md](integration-checklist.md) item 1 (**required**) and item 2.

## Connection direction

**The Pi backend calls the AMD endpoints**, not the other way around. AMD never needs to reach the Pi; your endpoints only need to be reachable over HTTPS from the internet.

Send Yosua:
- `AI_BASE_URL`, e.g. `https://xxxx.amd-cloud.example/`
- `AI_API_KEY` (by DM, **never** in the group or repo)

Every request carries the header `Authorization: Bearer <AI_API_KEY>`.

The backend is already wired up: until `AI_BASE_URL` is set it runs in **mock mode** (sample transcript + keyword classifier). Once the URL and key are in `.env`, it switches to your endpoints with no code change. If your endpoint errors or times out, classification falls back to keywords so the flow never stalls.

## 1. `POST /transcribe`

Telegram voice note → text.

**Request:** `multipart/form-data`, field `file` = `.ogg` audio (Opus, from Telegram, usually 3–15 s, Indonesian speech).

**Response**
```json
{"text": "motor panas, nunggu teknisi", "language": "id"}
```

## 2. `POST /classify`

Reason text → downtime category.

**Request**
```json
{"text": "motor panas, nunggu teknisi", "machine_id": "m1"}
```

**Response**
```json
{"category": "Breakdown – Overheat", "confidence": 0.86}
```

`category` **must be exactly** one of these 7 values. They are the stored database values; the backend maps them to the English labels shown on the dashboard and in the bot:

| `category` (send this) | Shown as |
|---|---|
| `Breakdown – Mekanik` | Breakdown – Mechanical |
| `Breakdown – Listrik` | Breakdown – Electrical |
| `Breakdown – Overheat` | Breakdown – Overheat |
| `Ganti produk/setup` | Changeover / setup |
| `Tunggu material` | Waiting for material |
| `Istirahat/terjadwal` | Break / scheduled |
| `Lainnya` | Other |

Note: the separator is an **en dash** `–`, not a hyphen `-`. Any other value is stored as `Lainnya` (Other).

If `confidence < 0.6`, the backend marks the stop as **Needs review** on the dashboard. Target for `/transcribe` + `/classify` combined: **< 10 s**.

## 3. `POST /explain`

Anomaly alert → explanation for the operator, with sources from manuals and repair history (RAG).

**Request**
```json
{
  "alert_id": 4,
  "machine_id": "m2",
  "machine_name": "Pump",
  "ts": "2026-10-14T09:24:25Z",
  "score": 0.80,
  "features": {
    "vib_rms":   {"now": 0.55, "normal": 0.40, "z": 4.75},
    "temp_c":    {"now": 46.6, "normal": 45.3, "z": 2.09},
    "current_a": {"now": 2.33, "normal": 2.30, "z": 1.03}
  },
  "recent_events": [
    {"ts": "2026-10-14T09:10:12Z", "category": "Breakdown – Mekanik", "transcript": "seal pompa bocor, diganti dulu"}
  ]
}
```

**Response**
```json
{
  "summary": "Vibration rose 39% above normal while current and temperature stay normal, consistent with early bearing wear.",
  "actions": ["Check bearing noise and temperature", "Inspect mounting bolts", "Lubricate per manual section 6.2"],
  "urgency": "inspect within 24h",
  "sources": [
    {"title": "Centrifugal pump manual", "page": 42, "snippet": "Excessive vibration is usually caused by..."}
  ]
}
```

- Language: **English** (the bot and dashboard are in English).
- The bot posts this as a reply to the early-warning message on Telegram, and the dashboard shows it in the alert box with a "Check: …" line built from `sources`.
- Target < 15 s. If it fails, the existing rule-based explanation is kept.

## 4. Data for the "Running on AMD" page (`/ai-usage`)

So the backend can log AI usage, please include a `usage` field in **every** response:
```json
"usage": {"model": "Qwen2.5-7B-Instruct", "latency_ms": 820, "prompt_tokens": 312, "completion_tokens": 45, "gpu": "MI300X"}
```
For `/transcribe`, `prompt_tokens`/`completion_tokens` may be `null`, but fill in `model` (e.g. `whisper-large-v3`) and `latency_ms`.

## 5. Quick test

From a laptop, before handing over:
```
curl -H "Authorization: Bearer $AI_API_KEY" -F file=@voice.ogg $AI_BASE_URL/transcribe
curl -H "Authorization: Bearer $AI_API_KEY" -H "Content-Type: application/json" \
     -d '{"text":"material dari gudang belum datang"}' $AI_BASE_URL/classify
```
Real voice notes from the bot are on the Pi (`data/voice/event_*.ogg`). Ask Yosua if you want them for testing; they are not in the repo.

## Reminders

- Shut down the GPU instance when not in use. If the endpoint is down, the bot still saves voice notes so they can be reprocessed later.
- Never commit API keys to the repo.
