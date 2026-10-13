# Raspberry Pi · Setup & Operasional Backend

Panduan untuk peran 2 (dan cadangannya, peran 4) menyiapkan dan menjalankan backend SiagaMesin.
Sistem berjalan dengan **Docker Compose**, jadi cara yang sama juga bisa dipakai di laptop atau VPS.

## Ringkasan sistem

| Komponen | Jalan sebagai | Port | Akses |
|---|---|---|---|
| `db` PostgreSQL 17 | container | – | hanya di dalam Docker |
| `mqtt` Mosquitto | container | 1883 | jaringan lokal (ESP32) |
| `api` FastAPI | container | 8000 | lokal + Tailscale Funnel |
| `worker` | container | – | – |
| `bot` Telegram | container | – | – |
| `sim` simulator | container (**opsional**, profile `sim`) | – | – |
| Tailscale Funnel | service sistem | 443 → 8000 | internet (HTTPS) |

Semua container memakai `restart: unless-stopped`: otomatis menyala saat Raspi boot dan restart sendiri kalau crash.
Perangkat: Raspberry Pi 4B 4 GB, Debian 13 (trixie) 64-bit, hostname `yosua`.

## Struktur folder

```
SiagaMesin/
├── .env                  # rahasia, TIDAK masuk repo (salin dari .env.example)
├── .env.example
├── Dockerfile            # satu image Python untuk api, worker, bot, sim
├── docker-compose.yml
├── backend/
│   ├── requirements.txt
│   └── app/
│       ├── main.py       # API: /health, /machines
│       ├── worker.py     # MQTT → DB, deteksi berhenti & anomali
│       ├── anomaly.py    # skor anomali z-score
│       ├── notify.py     # pesan Telegram (pertanyaan, peringatan dini)
│       ├── bot.py        # jawaban operator, /status
│       ├── ai.py         # klien AMD /transcribe, /classify (+ mode mock)
│       └── db.py         # koneksi database yang menunggu DB siap
├── db/init.sql           # skema database lengkap (dijalankan otomatis saat DB pertama dibuat)
├── deploy/               # config mosquitto (+ file systemd lama, tidak dipakai)
├── tools/
│   ├── sim.py            # simulator 4 mesin
│   └── baseline.py       # hitung kondisi normal tiap mesin
└── data/voice/           # voice note operator, TIDAK masuk repo
```

---

## A. Setup dari nol

Semua perintah dijalankan di Raspi lewat SSH: `ssh yosua@yosua.local`.

### 1. Docker
```
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER
exit                       # logout, lalu SSH lagi supaya grup docker aktif
docker run --rm hello-world
```

### 2. Kode
```
mkdir -p ~/hackathon && cd ~/hackathon
git clone git@github.com:YosuaMW/SiagaMesin.git siagamesin
cd siagamesin
cp .env.example .env
chmod 600 .env
```

### 3. Bot Telegram
1. Telegram → **@BotFather** (centang biru) → `/newbot` → simpan token.
2. Isi token ke `.env` tanpa menampilkannya di layar:
   ```
   read -s -p "Paste token: " T && sed -i "s|^TELEGRAM_BOT_TOKEN=.*|TELEGRAM_BOT_TOKEN=$T|" .env && unset T && echo
   ```
3. Kirim `/start` ke bot, lalu ambil chat ID:
   ```
   T=$(grep ^TELEGRAM_BOT_TOKEN= .env | cut -d= -f2)
   curl -s "https://api.telegram.org/bot$T/getUpdates" | grep -o '"chat":{"id":-\?[0-9]*'; unset T
   ```
4. Isi `TELEGRAM_CHAT_ID=` di `.env` dengan angka tadi (`nano .env`).

**Token jangan pernah di-screenshot atau dikirim ke grup.** Kalau bocor: BotFather → `/revoke`.

### 4. Jalankan
```
docker compose up -d --build
docker compose ps
```
Build pertama ±2–10 menit. Lima service (`db`, `mqtt`, `api`, `worker`, `bot`) harus **Up**.

### 5. Tailscale Funnel (HTTPS publik)
```
curl -fsSL https://tailscale.com/install.sh | sh
sudo tailscale up                    # buka link yang muncul, login, klik Connect
sudo tailscale funnel --bg 8000      # kalau diminta, buka link /f/funnel lalu Enable
```
Alamat publik saat ini: `https://yosua.tailf140ab.ts.net`
Di console Tailscale → Machines → **⋯** pada `yosua` → **Disable key expiry**.

### 6. Baseline kondisi normal
Nyalakan simulator (atau rig asli), tunggu minimal 5 menit, lalu:
```
docker compose --profile sim up -d sim
docker compose exec worker python /app/tools/baseline.py --minutes 30
```
Ulangi setelah rig asli terpasang dan berjalan normal 15–30 menit.

---

## B. Perintah sehari-hari

Semua dari folder `~/hackathon/siagamesin`.

| Tujuan | Perintah |
|---|---|
| Status semua | `docker compose ps` |
| Log live worker | `docker compose logs -f worker` (keluar `Ctrl+C`, container tetap jalan) |
| Log terakhir bot | `docker compose logs bot --tail 50` |
| **Terapkan perubahan kode** | `docker compose up -d --build` |
| Nyalakan simulator | `docker compose --profile sim up -d sim` |
| Matikan simulator | `docker compose --profile sim stop sim` |
| Hitung ulang baseline | `docker compose exec worker python /app/tools/baseline.py --minutes 30` |
| Masuk database | `docker compose exec db psql -U siaga -d siagamesin` |
| Matikan semua | `docker compose down` (data database tetap aman di volume) |
| Nyalakan semua | `docker compose up -d` |

**Simulator** tidak menyala otomatis (profile `sim`). Kalau sedang jalan lalu Raspi restart, simulator ikut menyala lagi.
**Mulai Jumat (deploy) sampai penilaian selesai, simulator harus menyala**, supaya dashboard tidak kosong saat juri membuka.

**Simulator `m1`:** selama rig asli belum ada, simulator ikut mensimulasikan `m1` (`--with-m1` di `docker-compose.yml`). Setelah ESP32 tersambung, hapus `"--with-m1"` dari baris `command` service `sim`, lalu `docker compose --profile sim up -d sim`.

## C. Cek kesehatan

| Cek | Perintah / alamat | Hasil benar |
|---|---|---|
| API lokal | `curl -s localhost:8000/health` | `"status":"ok"` |
| API publik | `https://yosua.tailf140ab.ts.net/health` | `"status":"ok"` |
| Container | `docker compose ps` | Semua **Up**, `db` **healthy** |
| MQTT masuk | `docker compose exec mqtt mosquitto_sub -t "siagamesin/#" -v` | Pesan tiap detik |
| Bot | ketik `/status` di Telegram | Kondisi semua mesin |
| Tailscale | `tailscale funnel status` | proxy ke `127.0.0.1:8000` |
| Auto-start | `systemctl is-enabled docker tailscaled` | `enabled` ×2 |

**Pantau database live:**
```
watch -n 2 'docker compose exec -T db psql -U siaga -d siagamesin -c "SELECT machine_id AS id, status, round(anomaly_score::numeric,2) AS skor FROM machines ORDER BY 1;" -c "SELECT id, machine_id, start_ts::time(0) AS mulai, end_ts::time(0) AS selesai, category FROM events ORDER BY id DESC LIMIT 5;" -c "SELECT id, machine_id, ts::time(0), round(score::numeric,2) AS skor, resolved_ts::time(0) AS selesai FROM alerts ORDER BY id DESC LIMIT 5;"'
```

**Lead time peringatan dini** (untuk slide pitch):
```
docker compose exec -T db psql -U siaga -d siagamesin -c "SELECT a.id, a.machine_id, a.ts::time(0) AS alert, e.start_ts::time(0) AS berhenti, round(extract(epoch FROM e.start_ts - a.ts)) AS lead_detik, e.category FROM alerts a LEFT JOIN LATERAL (SELECT start_ts, category FROM events WHERE machine_id = a.machine_id AND start_ts >= a.ts ORDER BY start_ts LIMIT 1) e ON true ORDER BY a.id DESC LIMIT 10;"
```

## D. Menyambungkan AI dari peran 3

Selama `AI_BASE_URL` kosong, bot memakai **mode mock**: voice note diberi transkrip contoh dan kategori ditentukan dari kata kunci. Setelah peran 3 mengirim URL + API key:
```
grep -q "^AI_BASE_URL=" .env || echo "AI_BASE_URL=" >> .env
grep -q "^AI_API_KEY=" .env || echo "AI_API_KEY=" >> .env
sed -i "s|^AI_BASE_URL=.*|AI_BASE_URL=https://alamat-dari-peran3|" .env
read -s -p "Paste API key: " K && sed -i "s|^AI_API_KEY=.*|AI_API_KEY=$K|" .env && unset K && echo
docker compose up -d
docker compose logs bot --tail 3      # harus: (AI: AMD)
```
Kalau endpoint AMD error/mati, klasifikasi otomatis kembali ke kata kunci, jadi alur tidak macet.

## E. Cara kerja singkat

- **Deteksi berhenti:** `current_a < STOP_CURRENT_A` selama `STOP_SECONDS` → event baru. Mesin `live` ditanya lewat Telegram; mesin `replay` diisi alasan otomatis oleh simulator.
- **Jawaban operator:** teks atau voice note → `/transcribe` → `/classify` → kategori. Confidence < 0.6 → **Perlu dicek**. Semua panggilan AI tercatat di tabel `ai_calls`.
- **Deteksi anomali:** rata-rata 10 detik terakhir dibandingkan baseline (median & sebaran) tiap sensor → nilai z. `z ≥ 3` selama 5 detik → alert + peringatan dini Telegram; `z < 2` → kembali normal. `anomaly_score = z ÷ 6` (maks 1).
- **Restart aman:** event dan alert yang masih terbuka dilanjutkan setelah restart, dan program menunggu database siap saat boot.

## F. Troubleshooting

| Gejala | Penyebab | Solusi |
|---|---|---|
| Perubahan kode tidak berpengaruh | Image belum di-build ulang | `docker compose up -d --build` |
| `port is already allocated` | Proses lain memakai 8000/1883 (mis. service systemd lama) | `sudo systemctl disable --now mosquitto siagamesin-api siagamesin-worker siagamesin-bot siagamesin-sim` |
| Pesan Telegram dobel | Bot jalan 2× (container + proses lain) | Pastikan hanya container `bot` yang jalan |
| `CannotConnectNowError ... shutting down` di log | Terjadi saat Raspi dimatikan | Normal, abaikan |
| Paste kode panjang terpotong | Batas terminal | Kirim file via `scp`, atau paste per bagian lalu cek `wc -l` |
| IP Raspi berubah | DHCP | Pakai `yosua.local`, bukan IP |
| Semua mesin dianggap anomali | Baseline tidak cocok (mis. rig baru) | Jalankan normal 15–30 menit → hitung ulang baseline |
| Semua mesin ⚪ Offline di `/status` | Simulator mati & rig tidak mengirim data | `docker compose --profile sim up -d sim` |
| URL publik tidak bisa dibuka | API mati / Funnel off | `curl localhost:8000/health`, lalu `tailscale funnel status` |

## G. Keamanan

- `.env` berizin `600`, masuk `.gitignore` dan `.dockerignore` (tidak ikut repo maupun image). Begitu juga `data/`.
- Database tidak dibuka ke luar Docker; API memakai user `siaga` dan query berparameter.
- API publik hanya punya endpoint GET.
- Bot hanya menanggapi `TELEGRAM_CHAT_ID` yang terdaftar.
- Log container dibatasi 3 × 10 MB per service supaya SD card tidak penuh.
- MQTT masih tanpa password: aman untuk hotspot tim, **jangan** dipakai di WiFi publik.

## H. Rencana berikutnya

- [ ] Endpoint `/events`, `/alerts`, `/availability`, `/pareto` (menunggu `types.ts`)
- [ ] Sambung `/transcribe` + `/classify` asli (Rabu) dan `/explain` + `/score` (Kamis)
- [ ] Endpoint `/ai-usage` (data sudah tercatat di `ai_calls`)
- [ ] Username/password MQTT
- [ ] Backup harian `pg_dump` + retensi telemetry
- [ ] Bersihkan data uji sebelum demo
