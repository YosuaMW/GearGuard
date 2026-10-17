# Role 3 · AI Engineer (LLM & Speech on AMD)

Contract between the Raspberry Pi backend and the AI endpoints on AMD Developer Cloud.

> To agree on: see [integration-checklist.md](integration-checklist.md) item 1 (**required**) and item 2.

## How it runs (current setup)

Role 3's service in [`AI/`](../AI/) runs **on the Raspberry Pi as the `ai` container** (same Docker Compose as the backend). It needs no GPU because it calls AMD Token Factory over the internet.

```
bot / worker ──► ai :8001 ──► AMD Token Factory: Qwen3.8-27B   (/classify, /explain)
                    └────► stt :9000: Whisper on the Pi CPU   (/transcribe)
```

- **Keys:** the Token Factory key (`rc-...`) is `RADEON_API_KEY` in `AI/.env` on the Pi only. The backend calls the service with an internal key (`AI_SERVICE_KEY` = backend `AI_API_KEY`). Never commit either. Template: [`AI/.env.example`](../AI/.env.example).
- **Audio:** Token Factory rejects every audio request (`input_audio`, `audio_url` and `file` all fail at the gateway, tested 15 Oct), so `/transcribe` goes to Whisper (`WHISPER_BASE_URL`). Today that is the `stt` container on the Pi (faster-whisper, CPU, ~5 s per voice note). To run Whisper on an AMD GPU instead, serve `openai/whisper-large-v3` with vLLM on an AMD Developer Cloud droplet and point `WHISPER_BASE_URL` at it (`http://<ip>:8000/v1`).
- **Honest labels, please:** `usage.gpu` is currently always `"AMD Radeon Cloud"` and `backend` says `whisper-amd`, even when Whisper runs on the Pi. Make the label follow the backend actually used (e.g. `"Raspberry Pi CPU"`), since the dashboard shows it to judges.
- **Quota:** limits are per team key (20 requests/min plus a daily budget). The backend calls `/explain` only for machines in `EXPLAIN_SOURCES` and retries it once after 20 s.
- **Speed:** `/explain` currently takes ~30–50 s. A lower `reasoning_effort` would make it snappier for the demo.
- Mock mode still exists: empty `AI_BASE_URL` in the backend `.env` = sample transcript + keyword rules.

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

From the Pi (inside the `bot` container the env vars are already set), or from a laptop with the same values:
```
curl -H "Authorization: Bearer $AI_API_KEY" -F file=@voice.ogg $AI_BASE_URL/transcribe
curl -H "Authorization: Bearer $AI_API_KEY" -H "Content-Type: application/json" \
     -d '{"text":"material dari gudang belum datang"}' $AI_BASE_URL/classify
```
Real voice notes from the bot are on the Pi (`data/voice/event_*.ogg`). Ask role 2 (backend) if you want them for testing; they are not in the repo.

## Reminders

- Shut down the GPU instance when not in use. If the endpoint is down, the bot still saves voice notes so they can be reprocessed later.
- Never commit API keys to the repo.
