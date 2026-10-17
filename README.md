# GearGuard

**Log why machines stop, then learn to keep them from stopping again.**
AMD Developer Hackathon ACT III · Track: Intelligent Industry

GearGuard retrofits legacy factory machines with cheap current, vibration and temperature sensors. When a machine stops, the operator is asked why on Telegram and can answer by text or voice note. AI turns that answer into a downtime category. When the sensor pattern starts drifting, GearGuard sends an early warning, and an AI running on AMD explains it with citations from the machine's manual and repair history.

- **Dashboard:** https://gearguard-sky.vercel.app
- **Public API:** https://yosua.tailf140ab.ts.net (Swagger at `/docs`)

## How it works

1. **Machine stops.** The worker sees current drop below `STOP_CURRENT_A` and opens a stop event.
2. **Operator is asked.** The Telegram bot asks "why did M3 stop?". The operator replies with text or a voice note.
3. **Speech to text on the edge.** Whisper (faster-whisper, base) transcribes the voice note on the Raspberry Pi CPU.
4. **Classified on AMD.** Qwen3.8-27B on AMD Token Factory maps the answer to one of 7 downtime categories. Low confidence is flagged "Needs review".
5. **Early warning.** Z-score anomaly detection on each machine's baseline sends an early warning to Telegram and the dashboard.
6. **Explained with sources.** Qwen on AMD explains the alert (summary, actions, urgency). It uses BM25 retrieval over the machine's PDF manual and recent repair notes. The explanation is posted as a reply to the warning and shown on the dashboard.
7. **Reports.** The dashboard shows availability, the downtime Pareto, the timeline and every AI call ("Running on AMD").

## Architecture

```
ESP32 + sensors (SCT-013, MPU6050, LM35)
        │ MQTT over TLS
        ▼
Raspberry Pi 4B · edge gateway · Docker Compose
 ├─ mqtt    Mosquitto, login required (:1883 LAN, :8443 TLS)
 ├─ db      PostgreSQL (telemetry, events, alerts, baselines)
 ├─ worker  stores data, detects stops and anomalies
 ├─ bot     Telegram: asks operators, early warnings
 ├─ stt     Whisper speech-to-text on the Pi CPU
 ├─ ai      /transcribe, /classify, /explain + RAG on manuals
 │            └─► AMD Token Factory · Qwen3.8-27B
 ├─ sim     replay simulator for m2–m4
 └─ api     FastAPI :8000
              └─► Tailscale Funnel (HTTPS) ─► Dashboard on Vercel
```

| Task | Runs on | Model |
|---|---|---|
| Voice note → text | Raspberry Pi (edge) | faster-whisper base |
| Text → downtime category | AMD Token Factory | Qwen3.8-27B |
| Alert explanation with manual sources | AMD Token Factory | Qwen3.8-27B |
| Stop and anomaly detection | Raspberry Pi | z-score on a median/scale baseline |

Token Factory serves language models but not audio, so speech-to-text runs on the Pi next to the line.

## Machines

| ID | Machine | Source |
|---|---|---|
| m1 | Conveyor motor | **Live ESP32 rig** over public MQTT |
| m2 | Pump | Replay simulator |
| m3 | Mixer | Replay simulator |
| m4 | Compressor | Replay simulator |

## Status (17 Oct 2026)

- ✅ Live ESP32 rig (m1) streaming over public MQTT with TLS and login
- ✅ Stop detection → Telegram question → text/voice answer → Whisper (Pi) → Qwen (AMD) → category
- ✅ Early warnings with AI explanations citing PDF manuals (per-machine `MANUAL_MAP`) and repair history, posted as a Telegram reply and on the dashboard
- ✅ Dashboard live: overview, machines, reports (availability, Pareto), "Running on AMD" with per-call logging
- ✅ Alert limits editable from the dashboard (`PUT /machines/{id}/limits`, protected by an admin key)
- ✅ Docker Compose with auto-start on boot, public HTTPS via Tailscale Funnel

## Running

```
cp .env.example .env              # Telegram token, MQTT login, keys
cp AI/.env.example AI/.env        # Token Factory key, internal keys, MANUAL_MAP
# put PDF manuals in AI/manuals/  (not committed)
docker compose up -d --build
docker compose --profile sim up -d --build sim   # replay simulator for m2–m4
```
Full setup from a blank Pi: [docs/raspi-setup.md](docs/raspi-setup.md).

### Demo controls (simulator)

```
mosquitto_pub -u siaga -P "$MQTT_PASSWORD" -t siagamesin/sim/cmd -m "calm"                 # no random events
mosquitto_pub -u siaga -P "$MQTT_PASSWORD" -t siagamesin/sim/cmd -m "wear m3"              # drift → early warning
mosquitto_pub -u siaga -P "$MQTT_PASSWORD" -t siagamesin/sim/cmd -m "stop m4 20 material"  # forced stop
mosquitto_pub -u siaga -P "$MQTT_PASSWORD" -t siagamesin/sim/cmd -m "random"               # back to normal mode
```

## API

Read-only endpoints for the dashboard: `/health`, `/machines`, `/machines/{id}`, `/telemetry`, `/summary`, `/events`, `/alerts`, `/pareto`, `/availability`, `/ai-usage`.

The only write endpoint is `PUT /machines/{id}/limits`. It needs the `X-Admin-Key` header, and is turned off when `ADMIN_KEY` is empty. Details: [docs/role4-frontend.md](docs/role4-frontend.md).

## Connecting the hardware

The ESP32 publishes one JSON message per second to `siagamesin/m1/telemetry`:

```json
{"machine_id": "m1", "current_a": 1.8, "vib_rms": 0.42, "temp_c": 41.5}
```

| | Host | Port | Notes |
|---|---|---|---|
| Internet (recommended) | `yosua.tailf140ab.ts.net` | `8443` | TLS: use `WiFiClientSecure` |
| Same Wi-Fi as the Pi | `yosua.local` | `1883` | plain `WiFiClient` |

Username `siaga`; the password is shared privately. Wiring, example code and a test checklist: [docs/role1-hardware.md](docs/role1-hardware.md).

## Team & docs

| Role | Document |
|---|---|
| 1. Hardware & sensors | [docs/role1-hardware.md](docs/role1-hardware.md) |
| 2. Backend, edge gateway & bot | [docs/raspi-setup.md](docs/raspi-setup.md) |
| 3. AI engineer (AMD Token Factory) | [docs/role3-ai.md](docs/role3-ai.md) · [AI/README.md](AI/README.md) |
| 4. Frontend dashboard | [docs/role4-frontend.md](docs/role4-frontend.md) · [dashboard/](dashboard/) |
| Everyone | [docs/integration-checklist.md](docs/integration-checklist.md) |

## Repo rules

- **Never commit** `.env`, `AI/.env`, bot tokens, MQTT/database passwords or API keys. Use the `.env.example` files.
- Not committed either: `deploy/passwd` (MQTT password hashes), `data/` (voice notes), `AI/manuals/` (PDF manuals).
