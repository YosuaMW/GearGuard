# Raspberry Pi · Backend Setup & Operations

Guide for role 2 (and their backup, role 4) to set up and run the GearGuard backend.
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
| `ai` AI service (role 3) | container | 8001 | inside Docker only |
| `stt` Whisper speech-to-text | container | 9000 | inside Docker only |
| Tailscale Funnel | system service | 443 → 8000, 8443 → 1883 | internet (HTTPS API, MQTT over TLS) |

All containers use `restart: unless-stopped`: they start on boot and restart themselves if they crash.
Hardware: Raspberry Pi 4B 4 GB, Debian 13 (trixie) 64-bit, hostname `yosua`.

## Folder layout

```
GearGuard/
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
│       ├── ai.py         # client for the AI service: /transcribe, /classify, /explain (+ mock mode)
│       └── db.py         # database connection that waits for the DB to be ready
├── AI/                  # role 3 AI service: /transcribe, /classify, /explain (+ AI/.env, NOT committed)
├── stt/                 # Whisper speech-to-text on the Pi (faster-whisper, CPU)
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
git clone git@github.com:YosuaMW/GearGuard.git siagamesin
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
The first build takes ~2–10 minutes (the `ai` and `stt` images install ffmpeg, which is slow on a Pi). Seven services (`db`, `mqtt`, `api`, `worker`, `bot`, `ai`, `stt`) should be **Up**; start the simulator separately (section B). On first start `stt` downloads the Whisper model (~150 MB for `base`), so give it a minute.

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
| Apply `AI/.env` changes | `docker compose up -d --force-recreate ai` |
| AI service log | `docker compose logs --tail 30 ai \| grep -v health` |

The **simulator** is in profile `sim`, so `docker compose up -d` alone doesn't start it. Once started, **leave it running and it comes back after every reboot** (`restart: unless-stopped`). Only `docker compose stop sim` keeps it off.
**From Friday (deploy) until judging ends, the simulator must be running**, so the dashboard isn't empty when judges open it.

**Which early warnings go to Telegram:** `ALERT_NOTIFY_SOURCES` in `.env`. `live` = only the real rig (quiet, default); `live,replay` = m2–m4 too (for demos). Apply with `docker compose up -d --force-recreate worker`. Stop questions are only asked for `live` machines either way.

**Which alerts get an AI explanation:** `EXPLAIN_SOURCES` in `.env` (default `live,replay`). `/explain` takes up to ~50 s and shares the team's Token Factory quota, so `live` keeps AMD free for operator answers; switch to `live,replay` when demoing early warnings on m2–m4. Apply with `docker compose up -d --force-recreate worker`.

**Voice note language:** `STT_LANGUAGE` in `.env`: `en`, `id`, or empty for auto-detect. Apply with `docker compose up -d stt`.

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
| Containers | `docker ps --format "table {{.Names}}\t{{.Status}}"` | 8 **Up** (incl. `sim`, `ai`, `stt`), `db` and `ai` **healthy** |
| AI mode | `curl -s localhost:8000/summary \| grep -o '"ai_mode":"[a-z]*"'` | `"ai_mode":"amd"` |
| Speech-to-text | `docker compose exec stt python -c "import urllib.request;print(urllib.request.urlopen('http://localhost:9000/health').read().decode())"` | `"ok":true` + model + language |
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

## D. AI (role 3) and speech-to-text

```
bot / worker ──► ai (container, :8001) ──► AMD Token Factory: Qwen3.8-27B   (/classify, /explain)
                     │
                     └──► stt (container, :9000): Whisper on the Pi CPU    (/transcribe)
```

- Role 3's AI service lives in `AI/` and runs on the Pi as the `ai` container. It needs no GPU: it calls AMD Token Factory over the internet.
- Token Factory has no working audio model (every audio request is rejected by the gateway), so `/transcribe` uses Whisper in the `stt` container. Switching to Whisper on an AMD GPU later only means changing `WHISPER_BASE_URL` in `AI/.env`.
- The backend talks to `ai` with an internal key; the Token Factory key (`rc-...`) only lives in `AI/.env`.

**Setup** (once):
```
cp AI/.env.example AI/.env && chmod 600 AI/.env
read -s -p "Token Factory key (rc-...): " RK; echo
SK=$(openssl rand -hex 24); WK=$(openssl rand -hex 16)
sed -i "s|^RADEON_API_KEY=.*|RADEON_API_KEY=$RK|; s|^AI_SERVICE_KEY=.*|AI_SERVICE_KEY=$SK|; s|^WHISPER_API_KEY=.*|WHISPER_API_KEY=$WK|" AI/.env
for k in AI_BASE_URL AI_API_KEY STT_API_KEY; do grep -q "^$k=" .env || echo "$k=" >> .env; done
sed -i "s|^AI_BASE_URL=.*|AI_BASE_URL=http://ai:8001|; s|^AI_API_KEY=.*|AI_API_KEY=$SK|; s|^STT_API_KEY=.*|STT_API_KEY=$WK|" .env
unset RK SK WK
mkdir -p AI/manuals            # PDF manuals for /explain sources (optional)
docker compose up -d --build
docker compose logs bot --tail 3      # should say: (AI: AMD)
```
Empty `AI_BASE_URL` in `.env` = **mock mode** (sample transcript + keyword rules), useful when AMD is unavailable.

**Test each step:**
```
# classify (Qwen on AMD)
docker compose exec bot python -c "import os,httpx;r=httpx.post(os.environ['AI_BASE_URL']+'/classify',headers={'Authorization':'Bearer '+os.environ['AI_API_KEY']},json={'text':'waiting for material from the warehouse','machine_id':'m1'},timeout=40);print(r.status_code,r.text[:300])"
# transcribe (Whisper on the Pi), using a saved voice note
docker compose exec bot python -c "import os,glob,httpx;f=sorted(glob.glob('/app/data/voice/*.ogg'))[-1];r=httpx.post(os.environ['AI_BASE_URL']+'/transcribe',headers={'Authorization':'Bearer '+os.environ['AI_API_KEY']},files={'file':open(f,'rb')},timeout=60);print(r.status_code,r.text[:300])"
# explain: trigger an alert, then watch for "[AI] alert N explained"
docker compose exec -T mqtt mosquitto_pub -u siaga -P "$MQTT_PASSWORD" -t siagamesin/sim/cmd -m "wear m2"
docker compose logs -f --since 10s worker | grep -E "ANOMALI|AI\]|Explain"
```

**When AMD is slow or down**, nothing stalls: classification falls back to keywords (the stop is marked *Needs review*), and alerts keep their rule-based explanation. The worker retries `/explain` once after 20 s. Token Factory limits are **per team key** (20 requests/min plus a daily budget; check **Check Usage** on the Token Factory page), so don't load-test with it.

## E. How it works

- **Stop detection:** `current_a < STOP_CURRENT_A` for `STOP_SECONDS` → new event. `live` machines get a Telegram question; `replay` machines get a reason from the simulator.
- **Operator answers:** text or voice note → `/transcribe` (Whisper on the Pi) → `/classify` (Qwen on AMD) → category. Confidence < 0.6 → **Needs review**. Every AI call is logged in `ai_calls`. Categories are stored in the role 3 contract values and shown in English (`labels.py`).
- **AI explanations:** each new alert (for machines in `EXPLAIN_SOURCES`) is sent to `/explain` in the background; the summary and sources are saved on the alert (dashboard) and posted as a reply to the Telegram early warning.
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
| Bot says "AI offline: keyword classifier used" | `/classify` timed out or hit the rate limit (often while an `/explain` is running) | `docker compose logs --since 3m ai \| grep -v health`; use `EXPLAIN_SOURCES=live` |
| "Couldn't transcribe the voice note" | `stt` not ready (model still downloading) or failed | `docker compose logs --tail 10 stt`; wait for `Application startup complete` |
| `401 Invalid LLMGateway API token` in `ai` logs | Wrong Token Factory key | Copy the `rc-...` key with **Copy to clipboard** on the Token Factory page into `RADEON_API_KEY` in `AI/.env` |
| `429 Too Many Requests` in `ai` logs | Team key rate limit | Wait a minute; ask the team not to loop requests |
| Public URL won't open | API down / Funnel off | `curl localhost:8000/health`, then `tailscale funnel status` |

## G. Security

- `.env` has mode `600` and is in `.gitignore` and `.dockerignore` (never in the repo or the image). Same for `data/`.
- The database isn't exposed outside Docker; the API uses the `siaga` user and parameterised queries.
- The public API only has GET endpoints.
- The bot only answers the registered `TELEGRAM_CHAT_ID`.
- Container logs are capped at 3 × 10 MB per service so the SD card doesn't fill up.
- The Token Factory key only lives in `AI/.env` (mode `600`, not committed). Services talk to each other with random internal keys; `ai` and `stt` aren't exposed outside Docker.
- MQTT requires a username/password (`deploy/passwd`, not committed). From the internet it is only reachable through Funnel on `:8443` with TLS.

## H. Remaining work

- [x] Real `/transcribe` (Whisper on the Pi) + `/classify` and `/explain` (Qwen on AMD)
- [ ] Optional: Whisper on an AMD GPU instance (`WHISPER_BASE_URL`)
- [ ] Live `m1` from the ESP32 rig + recompute baseline (role 1)
- [ ] Measure pitch numbers with `tools/metrics.py` once there is enough data
- [ ] Friday: keep the simulator running · Saturday: clear test data before recording
