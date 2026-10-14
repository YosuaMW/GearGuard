# Raspberry Pi · Backend Setup & Operations

Guide for role 2 (and their backup, role 4) to set up and run the SiagaMesin backend.
Everything runs with **Docker Compose**, so the same steps also work on a laptop or VPS.

## System overview

| Component | Runs as | Port | Reachable from |
|---|---|---|---|
| `db` PostgreSQL 17 | container | – | inside Docker only |
| `mqtt` Mosquitto (login required) | container | 1883 | local network + Tailscale Funnel (TLS :8443) |
| `api` FastAPI | container | 8000 | local + Tailscale Funnel |
| `worker` | container | – | – |
| `bot` Telegram | container | – | – |
| `sim` simulator (m2–m4) | container (profile `sim`) | – | – |
| Tailscale Funnel | system service | 443 → 8000, 8443 → 1883 | internet (HTTPS API, MQTT over TLS) |

All containers use `restart: unless-stopped`: they start on boot and restart themselves if they crash.
Hardware: Raspberry Pi 4B 4 GB, Debian 13 (trixie) 64-bit, hostname `yosua`.

## Folder layout

```
SiagaMesin/
├── .env                  # secrets, NOT committed (copy from .env.example)
├── .env.example
├── Dockerfile            # one Python image for api, worker, bot, sim
├── docker-compose.yml
├── backend/
│   ├── requirements.txt
│   └── app/
│       ├── main.py       # API: /machines, /telemetry, /summary, /events, /alerts, /pareto, /availability, /ai-usage
│       ├── labels.py     # English category labels, shift / time-range helpers
│       ├── worker.py     # MQTT → DB, stop & anomaly detection
│       ├── anomaly.py    # z-score anomaly scoring
│       ├── notify.py     # Telegram messages (stop questions, early warnings)
│       ├── bot.py        # operator answers, /status
│       ├── ai.py         # AMD client for /transcribe, /classify (+ mock mode)
│       └── db.py         # database connection that waits for the DB to be ready
├── db/init.sql           # full schema (runs automatically when the DB is first created)
├── deploy/               # mosquitto.conf, passwd (MQTT logins, NOT committed) (+ old systemd files, unused)
├── tools/
│   ├── sim.py            # simulator for m2–m4 (MQTT commands: wear / stop / calm)
│   ├── metrics.py        # numbers for the pitch slides
│   └── baseline.py       # computes each machine's normal condition
└── data/voice/           # operator voice notes, NOT committed
```

---

## A. Setup from scratch

Run everything on the Pi over SSH: `ssh yosua@yosua.local`.

### 1. Docker
```
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER
exit                       # log out, then SSH in again so the docker group applies
docker run --rm hello-world
```

### 2. Code
```
mkdir -p ~/hackathon && cd ~/hackathon
git clone git@github.com:YosuaMW/SiagaMesin.git siagamesin
cd siagamesin
cp .env.example .env
chmod 600 .env
```

### 3. Telegram bot
1. Telegram → **@BotFather** (blue check) → `/newbot` → keep the token.
2. Put the token in `.env` without showing it on screen:
   ```
   read -s -p "Paste token: " T && sed -i "s|^TELEGRAM_BOT_TOKEN=.*|TELEGRAM_BOT_TOKEN=$T|" .env && unset T && echo
   ```
3. Send `/start` to the bot, then get the chat ID:
   ```
   T=$(grep ^TELEGRAM_BOT_TOKEN= .env | cut -d= -f2)
   curl -s "https://api.telegram.org/bot$T/getUpdates" | grep -o '"chat":{"id":-\?[0-9]*'; unset T
   ```
4. Set `TELEGRAM_CHAT_ID=` in `.env` to that number (`nano .env`).

**Never screenshot the token or post it in a group.** If it leaks: BotFather → `/revoke`.

### 4. MQTT login
Mosquitto only accepts clients with a username/password. Create the password file and put the same password in `.env`:
```
P=$(openssl rand -hex 8); echo "MQTT password: $P"
docker run --rm -v "$PWD/deploy:/m" eclipse-mosquitto:2 mosquitto_passwd -c -b /m/passwd siaga "$P"
sudo chown 1883:1883 deploy/passwd && sudo chmod 600 deploy/passwd
sed -i "s/^MQTT_PASSWORD=.*/MQTT_PASSWORD=$P/" .env
```
`deploy/passwd` is in `.gitignore`. Share the password with role 1 privately (for the ESP32), never in the repo.

### 5. Start
```
docker compose up -d --build
docker compose ps
```
The first build takes ~2–10 minutes. Five services (`db`, `mqtt`, `api`, `worker`, `bot`) should be **Up**.

### 6. Tailscale Funnel (public API + MQTT)
```
curl -fsSL https://tailscale.com/install.sh | sh
sudo tailscale up                    # open the link shown, log in, click Connect
sudo tailscale funnel --bg 8000      # API; if asked, open the /f/funnel link and click Enable
sudo tailscale funnel --bg --tls-terminated-tcp=8443 tcp://localhost:1883   # MQTT over TLS
```
Public addresses: API `https://yosua.tailf140ab.ts.net`, MQTT `yosua.tailf140ab.ts.net:8443` (TLS, login required). Both survive reboots.
Turn public MQTT off: `sudo tailscale funnel --tls-terminated-tcp=8443 off`.
In the Tailscale console → Machines → **⋯** on `yosua` → **Disable key expiry**.

### 7. Normal-condition baseline
Start the simulator (or the real rig), wait at least 5 minutes, then:
```
docker compose --profile sim up -d sim
docker compose exec worker python /app/tools/baseline.py --minutes 30
```
Repeat once the real rig is connected and has run normally for 15–30 minutes.

---

## B. Daily commands

All from `~/hackathon/siagamesin`.

| Goal | Command |
|---|---|
| Status of everything | `docker compose ps` |
| Live worker log | `docker compose logs -f worker` (exit with `Ctrl+C`, the container keeps running) |
| Recent bot log | `docker compose logs bot --tail 50` |
| **Apply code changes** | `docker compose up -d --build` |
| Start the simulator | `docker compose --profile sim up -d sim` (add `--force-recreate` after changing `.env`) |
| Stop the simulator | `docker compose --profile sim stop sim` (stays off after reboot) |
| Recompute baseline | `docker compose exec worker python /app/tools/baseline.py --minutes 30` |
| Open the database | `docker compose exec db psql -U siaga -d siagamesin` |
| Stop everything | `docker compose down` (database data stays in the volume) |
| Start everything | `docker compose up -d` |
| Apply `.env` changes | `docker compose up -d --force-recreate worker bot api` |

The **simulator** is in profile `sim`, so `docker compose up -d` alone doesn't start it. Once started, **leave it running and it comes back after every reboot** (`restart: unless-stopped`). Only `docker compose stop sim` keeps it off.
**From Friday (deploy) until judging ends, the simulator must be running**, so the dashboard isn't empty when judges open it.

**Which early warnings go to Telegram:** `ALERT_NOTIFY_SOURCES` in `.env`. `live` = only the real rig (quiet, default); `live,replay` = m2–m4 too (for demos). Apply with `docker compose up -d --force-recreate worker`. Stop questions are only asked for `live` machines either way.

**MQTT commands need the login.** Load it once per terminal with `source .env`, then add `-u siaga -P "$MQTT_PASSWORD"` to every `mosquitto_sub` / `mosquitto_pub`.

**Simulator commands** (no restart needed), sent with `docker compose exec mqtt mosquitto_pub -u siaga -P "$MQTT_PASSWORD" -t siagamesin/sim/cmd -m "<command>"`:

| Command | Effect |
|---|---|
| `calm` | No random events, every machine runs normally |
| `random` | Random stops and bearing wear again |
| `wear m2 [s]` | Pump starts bearing wear now → early warning → stops after `s` seconds (default 90) |
| `stop m4 40 material` | Compressor stops for 40 s; reasons: `material`, `setup`, `break`, `electrical`, `overheat`, `other` |
| `status` | Prints every machine's phase (`docker compose logs sim --tail 1`) |

**`m1` = live ESP32 rig.** The simulator only covers m2–m4. While the rig is unplugged, `m1` shows as `stopped` with `online: false`. To simulate `m1` again (no rig available), add `"--with-m1"` back to the `sim` service `command` in `docker-compose.yml` and run `docker compose --profile sim up -d sim`.

**Connecting the ESP32:** from any network to `yosua.tailf140ab.ts.net:8443` (TLS), or on the same Wi-Fi to `yosua.local:1883`; login required on both. Watch it arrive with `docker compose exec mqtt mosquitto_sub -u siaga -P "$MQTT_PASSWORD" -t "siagamesin/m1/#" -v`. The first real data will likely trigger false early warnings until the baseline is recomputed (section A.7). Details: [role1-hardware.md](role1-hardware.md).

**Change the MQTT password** (e.g. if it leaked): repeat section A.4 with `sudo rm deploy/passwd` first, then `docker compose up -d --force-recreate mqtt worker` and `docker compose --profile sim up -d --force-recreate sim`. Send the new password to role 1.

**Pitch numbers:** `docker compose exec worker python /app/tools/metrics.py --hours 24` (add `--live-only` for the real rig only).

## C. Health checks

| Check | Command / address | Expected |
|---|---|---|
| Local API | `curl -s localhost:8000/health` | `"status":"ok"` |
| Public API | `https://yosua.tailf140ab.ts.net/health` | `"status":"ok"` |
| All endpoints | `https://yosua.tailf140ab.ts.net/docs` | Swagger lists every endpoint |
| Containers | `docker ps --format "table {{.Names}}\t{{.Status}}"` | 6 **Up** (incl. `sim`), `db` **healthy** |
| MQTT traffic | `docker compose exec mqtt mosquitto_sub -u siaga -P "$MQTT_PASSWORD" -t "siagamesin/#" -v` | A message every second |
| MQTT login enforced | `docker compose exec mqtt mosquitto_sub -t "#" -C 1 -W 3` | `not authorised` |
| Bot | send `/status` on Telegram | All machines listed |
| Tailscale | `tailscale funnel status` | `https://…` → `127.0.0.1:8000` and `tcp://…:8443` → `localhost:1883` |
| Auto-start | `systemctl is-enabled docker tailscaled` | `enabled` ×2 |

**Watch the database live:**
```
watch -n 2 'docker compose exec -T db psql -U siaga -d siagamesin -c "SELECT machine_id AS id, status, round(anomaly_score::numeric,2) AS score FROM machines ORDER BY 1;" -c "SELECT id, machine_id, start_ts::time(0) AS started, end_ts::time(0) AS ended, category FROM events ORDER BY id DESC LIMIT 5;" -c "SELECT id, machine_id, ts::time(0), round(score::numeric,2) AS score, resolved_ts::time(0) AS resolved FROM alerts ORDER BY id DESC LIMIT 5;"'
```

**Early-warning lead time** (for the pitch slides):
```
docker compose exec -T db psql -U siaga -d siagamesin -c "SELECT a.id, a.machine_id, a.ts::time(0) AS alert, e.start_ts::time(0) AS stopped, round(extract(epoch FROM e.start_ts - a.ts)) AS lead_s, e.category FROM alerts a LEFT JOIN LATERAL (SELECT start_ts, category FROM events WHERE machine_id = a.machine_id AND start_ts >= a.ts ORDER BY start_ts LIMIT 1) e ON true ORDER BY a.id DESC LIMIT 10;"
```

## D. Connecting role 3's AI

While `AI_BASE_URL` is empty, the bot runs in **mock mode**: voice notes get a sample transcript and categories come from keywords. Once role 3 sends the URL and API key:
```
grep -q "^AI_BASE_URL=" .env || echo "AI_BASE_URL=" >> .env
grep -q "^AI_API_KEY=" .env || echo "AI_API_KEY=" >> .env
sed -i "s|^AI_BASE_URL=.*|AI_BASE_URL=https://address-from-role3|" .env
read -s -p "Paste API key: " K && sed -i "s|^AI_API_KEY=.*|AI_API_KEY=$K|" .env && unset K && echo
docker compose up -d
docker compose logs bot --tail 3      # should say: (AI: AMD)
```
If the AMD endpoint errors or is down, classification falls back to keywords so the flow never stalls.

## E. How it works

- **Stop detection:** `current_a < STOP_CURRENT_A` for `STOP_SECONDS` → new event. `live` machines get a Telegram question; `replay` machines get a reason from the simulator.
- **Operator answers:** text or voice note → `/transcribe` → `/classify` → category. Confidence < 0.6 → **Needs review**. Every AI call is logged in `ai_calls`. Categories are stored in the role 3 contract values and shown in English (`labels.py`).
- **Anomaly detection:** the 10-second average is compared with each sensor's baseline (median & spread) → z value. `z ≥ 3` for 5 seconds → alert + Telegram early warning; `z < 2` → back to normal. `anomaly_score = z ÷ 6` (max 1).
- **Availability:** run time ÷ (run time + unplanned stops) within the selected range. Scheduled breaks and offline time are excluded. Shifts start at 06:00, 14:00 and 22:00 WIB (`SHIFT_STARTS` in `.env`).
- **Safe restarts:** open events and alerts carry over after a restart, and every service waits for the database on boot.

## F. Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| Code change has no effect | Image not rebuilt | `docker compose up -d --build` |
| `port is already allocated` | Something else uses 8000/1883 (e.g. old systemd services) | `sudo systemctl disable --now mosquitto siagamesin-api siagamesin-worker siagamesin-bot siagamesin-sim` |
| Duplicate Telegram messages | Bot running twice (container + another process) | Make sure only the `bot` container runs |
| `CannotConnectNowError ... shutting down` in logs | Happens while the Pi shuts down | Normal, ignore |
| Long pasted code gets cut off | Terminal limit | Paste in parts and check `wc -l` / `md5sum`, or copy the file with `scp` |
| Pi IP changed | DHCP | Use `yosua.local`, not the IP |
| Every machine flagged as anomalous | Baseline doesn't match (e.g. new rig) | Run normally for 15–30 min → recompute baseline |
| All machines ⚪ Offline in `/status` | Simulator off and rig not sending | `docker compose --profile sim up -d sim` |
| `Not authorized` / `not authorised` in sim or worker logs | Missing or wrong MQTT login | Check `MQTT_PASSWORD` in `.env` matches `deploy/passwd`; rebuild the sim image after code changes: `docker compose --profile sim up -d --build sim` |
| `mosquitto_sub` hangs with no output | Nothing is publishing (e.g. sim stopped or rejected) | Add `-W 10` to time out; check `docker compose logs sim --tail 5` |
| Public URL won't open | API down / Funnel off | `curl localhost:8000/health`, then `tailscale funnel status` |

## G. Security

- `.env` has mode `600` and is in `.gitignore` and `.dockerignore` (never in the repo or the image). Same for `data/`.
- The database isn't exposed outside Docker; the API uses the `siaga` user and parameterised queries.
- The public API only has GET endpoints.
- The bot only answers the registered `TELEGRAM_CHAT_ID`.
- Container logs are capped at 3 × 10 MB per service so the SD card doesn't fill up.
- MQTT requires a username/password (`deploy/passwd`, not committed). From the internet it is only reachable through Funnel on `:8443` with TLS.

## H. Remaining work

- [ ] Connect real `/transcribe` + `/classify` (role 3), then `/explain`
- [ ] Live `m1` from the ESP32 rig + recompute baseline (role 1)
- [ ] Measure pitch numbers with `tools/metrics.py` once there is enough data
- [ ] Friday: keep the simulator running · Saturday: clear test data before recording
