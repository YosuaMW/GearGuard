# GearGuard

**Log why machines stop, then learn to keep them from stopping again.**
AMD Developer Hackathon ACT III · Track: Intelligent Industry

GearGuard monitors legacy factory machines through current, vibration and temperature sensors. When a machine stops, the operator is asked why on Telegram (text or voice note). When the sensor pattern starts drifting, the system sends an early warning before the machine fails.

## Architecture

```
ESP32 + sensors ──MQTT──► Raspberry Pi (edge gateway, Docker Compose)
                           ├─ mqtt   : Mosquitto broker (login required; :1883 LAN, :8443 TLS via Funnel)
                           ├─ db     : PostgreSQL (telemetry, events, alerts, baselines, ai_calls)
                           ├─ worker : stores data, detects stops and anomalies
                           ├─ bot    : Telegram (asks operators, /status, early warnings)
                           ├─ ai     : role 3 AI service ──► AMD Token Factory (Qwen3.8-27B: /classify, /explain)
                           ├─ stt    : Whisper speech-to-text on the Pi CPU (/transcribe)
                           └─ api    : FastAPI (:8000) ──Tailscale Funnel──► public HTTPS ──► Dashboard (Vercel)
```

## Docs by role

| Role | Document | Contents |
|---|---|---|
| 1. Hardware & anomaly model | [docs/role1-hardware.md](docs/role1-hardware.md) | MQTT format, ESP32 example, `/score`, data recording |
| 2. Backend & bot | [docs/raspi-setup.md](docs/raspi-setup.md) | Raspberry Pi setup from scratch, daily commands, troubleshooting |
| 3. AI engineer | [docs/role3-ai.md](docs/role3-ai.md) | `/transcribe`, `/classify`, `/explain` contracts, usage data |
| 4. Frontend | [docs/role4-frontend.md](docs/role4-frontend.md) | API URL, every endpoint, dashboard page → endpoint map |
| Everyone | [docs/integration-checklist.md](docs/integration-checklist.md) | **What still needs to be agreed between roles, with deadlines** |

## Status (15 Oct 2026)

- ✅ MQTT → database, stop detection, Telegram bot asks the operator
- ✅ Operator text & voice answers → Whisper (Pi) → Qwen3.8-27B on AMD Token Factory → downtime category
- ✅ Early warnings explained by Qwen with repair-history sources, posted on Telegram and the dashboard
- ✅ 4 machines: m1 Conveyor motor (live rig), m2 Pump, m3 Mixer, m4 Compressor (replay simulator)
- ✅ Z-score anomaly detection + detailed Telegram early warnings, `/status` command
- ✅ Dashboard API: `/machines`, `/telemetry`, `/summary`, `/events`, `/alerts`, `/pareto`, `/availability`, `/ai-usage`
- ✅ CORS, public HTTPS via Tailscale Funnel, Docker Compose with auto-start on boot (simulator included)
- ✅ MQTT with username/password, reachable from the internet over TLS (`:8443`)
- ✅ Dashboard live at https://gearguard-sky.vercel.app (code in [`dashboard/`](dashboard/))
- ⏳ Live ESP32 rig (role 1), PDF manuals for `/explain` sources (role 3/5), optional Whisper on an AMD GPU

## Running

```
cp .env.example .env                       # fill in the Telegram token, etc.
docker compose up -d --build
docker compose --profile sim up -d sim     # optional: replay machine simulator
```
Full details: [docs/raspi-setup.md](docs/raspi-setup.md). API docs (Swagger): `http://localhost:8000/docs`.

## Connecting the hardware

The ESP32 on the live rig publishes one JSON message per second to MQTT topic `siagamesin/m1/telemetry`. It can connect from **any network** (phone hotspot, campus Wi-Fi):

| | Host | Port | Notes |
|---|---|---|---|
| Internet (recommended) | `yosua.tailf140ab.ts.net` | `8443` | TLS: use `WiFiClientSecure` |
| Same Wi-Fi as the Pi | `yosua.local` | `1883` | plain `WiFiClient` |

Username `siaga`; the password is shared privately by Yosua (never in the repo).

```json
{"machine_id": "m1", "current_a": 1.8, "vib_rms": 0.42, "temp_c": 41.5}
```

The backend stores it, detects stops and anomalies, asks the operator on Telegram and serves it to the dashboard. The simulator only covers m2–m4, so it never clashes with the rig. Wiring (PZEM-004T, MPU6050, LM35), example code and a test checklist: [docs/role1-hardware.md](docs/role1-hardware.md).

## Repo rules

- **Never commit `.env`**, bot tokens, database/MQTT passwords or API keys. Use `.env.example`.
- `deploy/passwd` (MQTT password hashes) is not committed either.
- The `data/` folder (operator voice notes) is not committed.
