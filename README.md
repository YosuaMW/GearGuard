# SiagaMesin

**Mencatat kenapa mesin berhenti, lalu belajar untuk mencegahnya berhenti lagi.**
AMD Developer Hackathon ACT III · Track: Intelligent Industry

SiagaMesin memantau mesin pabrik lama lewat sensor arus, getaran, dan suhu. Saat mesin berhenti, operator ditanya alasannya lewat Telegram (teks atau voice note). Saat pola sensor mulai menyimpang, sistem mengirim peringatan dini sebelum mesin rusak.

## Arsitektur

```
ESP32 + sensor ──MQTT──► Raspberry Pi (edge gateway)
                          ├─ Mosquitto (MQTT broker, :1883, hanya jaringan lokal)
                          ├─ PostgreSQL (telemetry, events, alerts, baselines)
                          ├─ worker  : simpan data, deteksi berhenti, deteksi anomali
                          ├─ bot     : Telegram (tanya operator, /status, peringatan)
                          └─ API     : FastAPI (:8000) ──Tailscale Funnel──► HTTPS publik
                                          │                                  │
                         AMD Developer Cloud ◄── dipanggil backend      Dashboard (Vercel)
                         (/transcribe, /classify, /explain)
```

## Dokumen per peran

| Peran | Dokumen | Isi |
|---|---|---|
| 1. Hardware & Model Anomali | [docs/peran1-hardware.md](docs/peran1-hardware.md) | Format MQTT, contoh kode ESP32, `/score`, rekaman data |
| 2. Backend & Bot | [docs/raspi-setup.md](docs/raspi-setup.md) | Setup Raspi dari nol, cara menjalankan, troubleshooting |
| 3. AI Engineer | [docs/peran3-ai.md](docs/peran3-ai.md) | Kontrak `/transcribe`, `/classify`, `/explain`, data usage |
| 4. Frontend | [docs/peran4-frontend.md](docs/peran4-frontend.md) | URL API, bentuk JSON, status endpoint |
| Semua | [docs/checklist-integrasi.md](docs/checklist-integrasi.md) | **Hal yang perlu disepakati antar-peran + deadline** |

## Status (13 Okt 2026)

- ✅ MQTT → database, deteksi mesin berhenti, bot Telegram bertanya
- ✅ Jawaban teks & voice note operator tersimpan
- ✅ 4 mesin (m1 live, m2–m4 replay simulator)
- ✅ Deteksi anomali z-score + peringatan dini detail di Telegram, perintah `/status`
- ✅ `/machines` sesuai format frontend, CORS, HTTPS publik via Tailscale Funnel
- ⏳ `/events`, `/alerts`, `/availability`, `/pareto` (menunggu `types.ts`)
- ⏳ Integrasi `/transcribe` + `/classify` (Rabu) dan `/explain` + `/score` (Kamis)

## Aturan repo

- **Jangan pernah commit `.env`**, token bot, password database, atau API key. Gunakan `.env.example`.
- Folder `data/` (voice note operator) tidak masuk repo.
