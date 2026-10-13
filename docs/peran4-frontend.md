# Peran 4 · Frontend Dashboard

> Yang perlu disepakati: lihat [checklist-integrasi.md](checklist-integrasi.md) poin 3 (Rabu).

## Alamat API

| Kondisi | Base URL |
|---|---|
| Dari mana saja (HTTPS) | `https://yosua.tailf140ab.ts.net` |
| Satu WiFi dengan Raspi | `http://yosua.local:8000` |

Dokumentasi interaktif (Swagger): `<base URL>/docs`

Simpan base URL di environment variable dashboard (mis. `NEXT_PUBLIC_API_URL`), jangan di-hardcode.

API hidup selama Raspi menyala dan proses API jalan. Kalau tidak bisa diakses, kabari Yosua.

## CORS

Origin yang diizinkan: `http://localhost:3000`. **Kirim URL Vercel ke Yosua** setelah deploy supaya ditambahkan.

Semua endpoint hanya **GET** (baca saja).

## Format umum

- Waktu: ISO 8601 dengan zona, selalu UTC (mis. `2026-10-13T09:24:25.123+00:00`). Aman dibaca `new Date()`. Tampilkan dalam WIB di UI.
- Angka sensor bisa `null` kalau sensor belum mengirim data.

## `GET /machines` ✅ sudah tersedia

Polling tiap 1 detik.

```json
[
  {
    "id": "m4",
    "name": "Conveyor B",
    "source": "replay",
    "status": "anomaly",
    "anomaly_score": 0.8,
    "awaiting_reason": false,
    "stopped_since": null,
    "last": {
      "machine_id": "m4",
      "ts": "2026-10-13T09:24:25+00:00",
      "current_a": 1.63,
      "vib_rms": 0.62,
      "temp_c": 41.7
    }
  }
]
```

| Field | Keterangan |
|---|---|
| `source` | `live` = rig asli (m1), `replay` = simulator (m2–m4) |
| `status` | `running` / `anomaly` / `stopped` |
| `anomaly_score` | 0–1. < 0.5 normal, ≥ 0.5 waspada, status `anomaly` = terkonfirmasi. Bisa `null` sebelum baseline ada |
| `awaiting_reason` | `true` kalau bot sudah bertanya ke operator tapi belum dijawab (tanda merah "waiting for reply"). Tetap `true` walau mesin sudah jalan lagi, sampai operator menjawab |
| `stopped_since` | Waktu mulai berhenti, hanya terisi saat `status = stopped` |
| `last` | Data sensor terakhir; `null` kalau mesin belum pernah mengirim data |

Mesin aktif saat ini: `m1` Motor Demo 1 (live), `m2` Mixer Motor, `m3` Water Pump, `m4` Conveyor B (replay).

## ⏳ Endpoint yang sedang dibuat

Mengikuti `src/lib/types.ts`. **Kirim isi file itu ke Yosua**, plus rentang waktu yang diinginkan untuk Availability/Pareto (1 jam / 8 jam / per shift).

| Endpoint | Polling | Isi (rencana) |
|---|---|---|
| `GET /events` | 2 s | Riwayat berhenti: mesin, mulai, selesai, durasi, transcript, kategori, confidence, `needs_review` |
| `GET /alerts` | 2 s | Peringatan anomali: mesin, waktu, skor, nilai per sensor, penjelasan AI + sumber, selesai |
| `GET /availability` | 10 s | Per mesin: waktu jalan ÷ waktu rencana |
| `GET /pareto` | 10 s | Total durasi downtime per kategori, urut terbesar |
| `GET /ai-usage` | – | Jumlah panggilan, latensi rata-rata, token per model (Kamis, bareng peran 3) |

Kategori downtime (7 + 1):
`Breakdown – Mekanik`, `Breakdown – Listrik`, `Breakdown – Overheat`, `Ganti produk/setup`, `Tunggu material`, `Istirahat/terjadwal`, `Lainnya`, dan `Perlu dicek` (confidence rendah).

## Tips tes

- Simulator membuat mesin replay berhenti dan mengalami "bearing aus" secara acak, jadi semua status akan muncul dalam beberapa menit.
- Kalau ingin melihat data yang sama dari sisi operator, minta diundang ke bot Telegram dan ketik `/status`.
