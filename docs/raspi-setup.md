# Raspberry Pi · Setup & Operasional Backend

Panduan untuk peran 2 (dan cadangannya, peran 4) menyiapkan dan menjalankan backend SiagaMesin di Raspberry Pi.

## Ringkasan sistem

| Komponen | Jalan sebagai | Port | Akses |
|---|---|---|---|
| PostgreSQL 17 | service sistem (otomatis saat boot) | 5432 | hanya localhost |
| Mosquitto (MQTT) | service sistem (otomatis saat boot) | 1883 | jaringan lokal |
| Tailscale Funnel | service sistem (otomatis saat boot) | 443 → 8000 | internet (HTTPS) |
| API FastAPI | proses Python (manual) | 8000 | lokal + Funnel |
| Worker | proses Python (manual) | – | – |
| Bot Telegram | proses Python (manual) | – | – |
| Simulator | proses Python (manual, opsional) | – | – |

Perangkat: Raspberry Pi 4B 4 GB, Debian 13 (trixie) 64-bit, hostname `yosua`.

## Struktur folder

```
~/hackathon/siagamesin/
├── .env                  # rahasia, TIDAK masuk repo
├── .env.example
├── .venv/                # virtualenv Python
├── backend/
│   ├── requirements.txt
│   └── app/
│       ├── main.py       # API: /health, /machines
│       ├── worker.py     # MQTT → DB, deteksi berhenti & anomali
│       ├── anomaly.py    # skor anomali z-score
│       ├── notify.py     # kirim pesan Telegram (pertanyaan, peringatan)
│       └── bot.py        # terima jawaban operator, /status
├── db/init.sql           # skema database lengkap
├── tools/
│   ├── sim.py            # simulator 4 mesin
│   └── baseline.py       # hitung kondisi normal tiap mesin
└── data/voice/           # voice note operator, TIDAK masuk repo
```

---

## A. Setup dari nol

Lakukan sekali saja. Semua perintah dijalankan di Raspi lewat SSH: `ssh yosua@yosua.local`.

### 1. Paket sistem
```
sudo apt update
sudo apt install -y python3-venv python3-pip mosquitto mosquitto-clients postgresql
```

### 2. Mosquitto boleh diakses ESP32 di jaringan lokal
```
echo -e "listener 1883 0.0.0.0\nallow_anonymous true" | sudo tee /etc/mosquitto/conf.d/esp.conf
sudo systemctl restart mosquitto
```

### 3. Kode + virtualenv
```
mkdir -p ~/hackathon && cd ~/hackathon
git clone <url-repo-tim> siagamesin
cd siagamesin
python3 -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements.txt
```

### 4. Database + user khusus (bukan superuser)
```
PASS=$(openssl rand -hex 16)
sudo -u postgres psql -c "CREATE USER siaga WITH PASSWORD '$PASS';"
sudo -u postgres psql -c "CREATE DATABASE siagamesin OWNER siaga;"
cp .env.example .env
sed -i "s/GANTI_PASSWORD/$PASS/" .env
chmod 600 .env
set -a; source .env; set +a
psql "$DATABASE_URL" -f db/init.sql
```

### 5. Bot Telegram
1. Telegram → **@BotFather** (centang biru) → `/newbot` → simpan token.
2. Isi token ke `.env` tanpa menampilkannya di layar:
   ```
   read -s -p "Paste token: " T && sed -i "s|^TELEGRAM_BOT_TOKEN=.*|TELEGRAM_BOT_TOKEN=$T|" .env && unset T && echo
   ```
3. Kirim `/start` ke bot, lalu ambil chat ID:
   ```
   set -a; source .env; set +a
   curl -s "https://api.telegram.org/bot$TELEGRAM_BOT_TOKEN/getUpdates" | grep -o '"chat":{"id":-\?[0-9]*'
   ```
4. Isi `TELEGRAM_CHAT_ID=` di `.env` dengan angka tadi (`nano .env`).

**Token jangan pernah di-screenshot atau dikirim ke grup.** Kalau bocor: BotFather → `/revoke`.

### 6. Tailscale Funnel (HTTPS publik)
```
curl -fsSL https://tailscale.com/install.sh | sh
sudo tailscale up                    # buka link yang muncul, login, klik Connect
sudo tailscale funnel --bg 8000      # kalau diminta, buka link /f/funnel lalu Enable
```
Alamat publik saat ini: `https://yosua.tailf140ab.ts.net`
Di console Tailscale → Machines → **⋯** pada `yosua` → **Disable key expiry**.

### 7. Baseline kondisi normal
Jalankan sistem + simulator minimal 5 menit, lalu:
```
python tools/baseline.py --minutes 30
```
Ulangi setelah rig asli terpasang dan berjalan normal 15–30 menit.

---

## B. Menjalankan sistem (setiap kali)

Buka **4 tab terminal**, SSH ke Raspi di masing-masing. Nyalakan berurutan:

```
# Terminal 1 · API
cd ~/hackathon/siagamesin/backend && source ../.venv/bin/activate
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

# Terminal 2 · Worker
cd ~/hackathon/siagamesin/backend && source ../.venv/bin/activate
python -m app.worker

# Terminal 3 · Bot
cd ~/hackathon/siagamesin/backend && source ../.venv/bin/activate
python -m app.bot

# Terminal 4 · Simulator (m1 ikut disimulasikan selama rig belum ada)
cd ~/hackathon/siagamesin && source .venv/bin/activate
python tools/sim.py --with-m1
```

Setelah rig asli tersambung, simulator dijalankan **tanpa** `--with-m1`.

**Mematikan semua proses:**
```
pkill -f "uvicorn app.main"; pkill -f "app.worker"; pkill -f "app.bot"; pkill -f "sim.py"
```

## C. Cek kesehatan

| Cek | Perintah / alamat | Hasil benar |
|---|---|---|
| API lokal | `curl -s localhost:8000/health` | `"status":"ok"` |
| API publik | `https://yosua.tailf140ab.ts.net/health` | `"status":"ok"` |
| Proses jalan | `pgrep -af "app.main\|app.worker\|app.bot\|sim.py"` | Masing-masing 1 (uvicorn bisa 2: reloader + server) |
| MQTT masuk | `mosquitto_sub -t "siagamesin/#" -v` | Pesan tiap detik |
| Bot | ketik `/status` di Telegram | Kondisi semua mesin |
| Database | `pg_lsclusters` | `online` |
| Tailscale | `tailscale status` / `tailscale funnel status` | `yosua` online, proxy ke :8000 |

**Pantau database live** (dari folder `siagamesin`, setelah `set -a; source .env; set +a`):
```
watch -n 2 'psql "$DATABASE_URL" -c "SELECT machine_id AS id, status, round(anomaly_score::numeric,2) AS skor FROM machines ORDER BY 1;" -c "SELECT id, machine_id, start_ts::time(0) AS mulai, end_ts::time(0) AS selesai, category FROM events ORDER BY id DESC LIMIT 5;" -c "SELECT id, machine_id, ts::time(0), round(score::numeric,2) AS skor, resolved_ts::time(0) AS selesai FROM alerts ORDER BY id DESC LIMIT 5;"'
```

**Lead time peringatan dini** (untuk slide pitch):
```
psql "$DATABASE_URL" -c "SELECT a.id, a.machine_id, a.ts::time(0) AS alert, e.start_ts::time(0) AS berhenti, round(extract(epoch FROM e.start_ts - a.ts)) AS lead_detik, e.category FROM alerts a LEFT JOIN LATERAL (SELECT start_ts, category FROM events WHERE machine_id = a.machine_id AND start_ts >= a.ts ORDER BY start_ts LIMIT 1) e ON true ORDER BY a.id DESC LIMIT 10;"
```

## D. Cara kerja singkat

- **Deteksi berhenti:** `current_a < STOP_CURRENT_A` selama `STOP_SECONDS` → event baru. Mesin `live` ditanya lewat Telegram; mesin `replay` diisi alasan otomatis dari simulator.
- **Deteksi anomali:** rata-rata 10 detik terakhir dibandingkan baseline (median & sebaran) tiap sensor → nilai z. `z ≥ 3` selama 5 detik → alert + peringatan dini Telegram; `z < 2` → kembali normal. `anomaly_score = z ÷ 6` (maks 1).
- **Restart aman:** saat worker dinyalakan, event dan alert yang masih terbuka dilanjutkan, jadi tidak ada event dobel atau alert "hantu".

## E. Troubleshooting

| Gejala | Penyebab | Solusi |
|---|---|---|
| `Address already in use` saat start API | API lama masih jalan | `pkill -f "uvicorn app.main"` lalu start ulang |
| Pesan Telegram dobel | Worker/bot jalan 2× | Matikan semua (`pkill`), nyalakan 1× |
| `role "yosua" does not exist` | `.env` belum dimuat | `set -a; source .env; set +a` |
| `IndentationError` setelah paste kode | Spasi ikut ter-copy | `sed -i 's/^   //' file.py`, atau paste ulang tanpa spasi depan |
| `SyntaxError` aneh di tengah file | Kode ter-paste 2× | `rm` file, `nano` ulang, paste sekali, cek `wc -l` |
| Heredoc `>` tidak selesai | `EOF` ber-spasi | `Ctrl+C`, pakai `printf` atau editor |
| IP Raspi berubah | DHCP | Pakai `yosua.local`, bukan IP |
| Semua mesin dianggap anomali | Baseline tidak cocok (mis. rig baru) | Jalankan normal 15–30 menit → `tools/baseline.py` |
| URL publik tidak bisa dibuka | API mati / Funnel off | Cek `localhost:8000/health`, lalu `tailscale funnel status` |

## F. Keamanan

- `.env` berizin `600` dan masuk `.gitignore`, begitu juga `data/`.
- PostgreSQL hanya mendengarkan localhost; API memakai user `siaga` (bukan superuser) dan query berparameter.
- API publik hanya punya endpoint GET.
- Bot hanya menanggapi `TELEGRAM_CHAT_ID` yang terdaftar.
- MQTT masih tanpa password: aman untuk hotspot tim, **jangan** dipakai di WiFi publik.

## G. Rencana berikutnya

- [ ] Service systemd untuk API, worker, bot (otomatis saat boot, tidak bisa jalan dobel)
- [ ] Endpoint `/events`, `/alerts`, `/availability`, `/pareto` (menunggu `types.ts`)
- [ ] Integrasi `/transcribe` + `/classify` (Rabu) dan `/explain` + `/score` (Kamis)
- [ ] Username/password MQTT
- [ ] Backup harian `pg_dump` + retensi telemetry
- [ ] Bersihkan data uji sebelum demo
