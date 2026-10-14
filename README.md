# SiagaMesin

**Log why machines stop, then learn to keep them from stopping again.**
AMD Developer Hackathon ACT III · Track: Intelligent Industry

SiagaMesin monitors legacy factory machines through current, vibration and temperature sensors. When a machine stops, the operator is asked why on Telegram (text or voice note). When the sensor pattern starts drifting, the system sends an early warning before the machine fails.

## Architecture

```
ESP32 + sensors ──MQTT──► Raspberry Pi (edge gateway, Docker Compose)
                           ├─ mqtt   : Mosquitto broker (:1883, local network only)
                           ├─ db     : PostgreSQL (telemetry, events, alerts, baselines, ai_calls)
                           ├─ worker : stores data, detects stops and anomalies
                           ├─ bot    : Telegram (asks operators, /status, early warnings)
                           └─ api    : FastAPI (:8000) ──Tailscale Funnel──► public HTTPS
                                          │                                   │
                         AMD Developer Cloud ◄── called by backend        Dashboard (Vercel)
                         (/transcribe, /classify, /explain)
```

## Docs by role

| Role | Document | Contents |
|---|---|---|
| 1. Hardware & anomaly model | [docs/role1-hardware.md](docs/role1-hardware.md) | MQTT format, ESP32 example, `/score`, data recording |
| 2. Backend & bot | [docs/raspi-setup.md](docs/raspi-setup.md) | Raspberry Pi setup from scratch, daily commands, troubleshooting |
| 3. AI engineer | [docs/role3-ai.md](docs/role3-ai.md) | `/transcribe`, `/classify`, `/explain` contracts, usage data |
| 4. Frontend | [docs/role4-frontend.md](docs/role4-frontend.md) | API URL, every endpoint, dashboard page → endpoint map |
| Everyone | [docs/integration-checklist.md](docs/integration-checklist.md) | **What still needs to be agreed between roles, with deadlines** |

## Status (14 Oct 2026)

- ✅ MQTT → database, stop detection, Telegram bot asks the operator
- ✅ Operator text & voice answers → downtime category (mock mode, ready for AMD)
- ✅ 4 machines: m1 Conveyor motor (live rig), m2 Pump, m3 Mixer, m4 Compressor (replay simulator)
- ✅ Z-score anomaly detection + detailed Telegram early warnings, `/status` command
- ✅ Dashboard API: `/machines`, `/telemetry`, `/summary`, `/events`, `/alerts`, `/pareto`, `/availability`, `/ai-usage`
- ✅ CORS, public HTTPS via Tailscale Funnel, Docker Compose with auto-start on boot
- ⏳ Real `/transcribe` + `/classify` (role 3), `/explain` (role 3), live ESP32 rig (role 1)

## Running

```
cp .env.example .env                       # fill in the Telegram token, etc.
docker compose up -d --build
docker compose --profile sim up -d sim     # optional: replay machine simulator
```
Full details: [docs/raspi-setup.md](docs/raspi-setup.md). API docs (Swagger): `http://localhost:8000/docs`.

## Repo rules

- **Never commit `.env`**, bot tokens, database passwords or API keys. Use `.env.example`.
- The `data/` folder (operator voice notes) is not committed.
