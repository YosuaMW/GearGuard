# Peran 3 · AI Engineer (LLM & Speech di AMD)

Kontrak antara backend Raspi dan endpoint AI di AMD Developer Cloud.

> Yang perlu disepakati: lihat [checklist-integrasi.md](checklist-integrasi.md) poin 1 (**wajib, Selasa malam**) dan poin 2 (Rabu).

## Arah koneksi

**Backend Raspi yang memanggil endpoint AMD**, bukan sebaliknya. Jadi AMD tidak perlu mengakses Raspi; cukup endpoint kamu bisa dijangkau lewat HTTPS dari internet.

Yang perlu dikirim ke Yosua:
- `AI_BASE_URL`, mis. `https://xxxx.amd-cloud.example/`
- `AI_API_KEY` (dikirim lewat DM, **bukan** grup/repo)

Semua request memakai header `Authorization: Bearer <AI_API_KEY>`.

## 1. `POST /transcribe`

Voice note Telegram → teks.

**Request:** `multipart/form-data`, field `file` = audio `.ogg` (Opus, dari Telegram, biasanya 3–15 detik).

**Respons**
```json
{"text": "motor panas, nunggu teknisi", "language": "id"}
```

## 2. `POST /classify`

Teks alasan → kategori downtime.

**Request**
```json
{"text": "motor panas, nunggu teknisi", "machine_id": "m1"}
```

**Respons**
```json
{"category": "Breakdown – Overheat", "confidence": 0.86}
```

`category` **wajib persis** salah satu dari 7 kategori ini (dipakai Pareto di dashboard):
1. `Breakdown – Mekanik`
2. `Breakdown – Listrik`
3. `Breakdown – Overheat`
4. `Ganti produk/setup`
5. `Tunggu material`
6. `Istirahat/terjadwal`
7. `Lainnya`

Catatan: tanda pisahnya **en dash** `–`, bukan tanda minus `-`.

Kalau `confidence < 0.6`, backend menandai event sebagai **"Perlu dicek"** di dashboard. Target total `/transcribe` + `/classify` **< 10 detik**.

## 3. `POST /explain` (Kamis)

Alert anomali → penjelasan untuk operator, dengan sumber dari manual + riwayat perbaikan (RAG).

**Request**
```json
{
  "alert_id": 4,
  "machine_id": "m4",
  "machine_name": "Conveyor B",
  "ts": "2026-10-13T09:24:25Z",
  "score": 0.80,
  "features": {
    "vib_rms":   {"now": 0.55, "normal": 0.40, "z": 4.75},
    "temp_c":    {"now": 41.6, "normal": 40.0, "z": 2.09},
    "current_a": {"now": 1.63, "normal": 1.60, "z": 1.03}
  },
  "recent_events": [
    {"ts": "2026-10-13T09:10:12Z", "category": "Breakdown – Mekanik", "transcript": "bearing aus, diganti teknisi"}
  ]
}
```

**Respons**
```json
{
  "summary": "Vibration rose 39% above normal while current and temperature stay normal, consistent with early bearing wear.",
  "actions": ["Check bearing noise and temperature", "Inspect mounting bolts", "Lubricate per manual section 6.2"],
  "urgency": "inspect within 24h",
  "sources": [
    {"title": "Motor manual XYZ", "page": 42, "snippet": "Excessive vibration is usually caused by..."}
  ]
}
```

- Bahasa: **Inggris** (bot sudah berbahasa Inggris).
- Bot akan mengirim jawaban ini sebagai balasan ke pesan peringatan dini di Telegram, dan dashboard menampilkannya di daftar alert.
- Target < 15 detik. Kalau gagal, bot tetap memakai penjelasan berbasis aturan yang sudah ada.

## 4. Data untuk halaman "Running on AMD" (`/ai-usage`)

Supaya backend bisa mencatat pemakaian AI, tolong sertakan field `usage` di **setiap** respons:
```json
"usage": {"model": "Qwen2.5-7B-Instruct", "latency_ms": 820, "prompt_tokens": 312, "completion_tokens": 45, "gpu": "MI300X"}
```
Untuk `/transcribe`, `prompt_tokens`/`completion_tokens` boleh `null`, tapi isi `model` (mis. `whisper-large-v3`) dan `latency_ms`.

## 5. Tes cepat

Dari laptop, sebelum diserahkan:
```
curl -H "Authorization: Bearer $AI_API_KEY" -F file=@voice.ogg $AI_BASE_URL/transcribe
curl -H "Authorization: Bearer $AI_API_KEY" -H "Content-Type: application/json" \
     -d '{"text":"material dari gudang belum datang"}' $AI_BASE_URL/classify
```
Contoh voice note asli dari bot ada di Raspi (`data/voice/event_*.ogg`). Minta ke Yosua kalau mau dipakai untuk uji, karena file ini tidak masuk repo.

## Pengingat

- Matikan instance GPU saat tidak dipakai (aturan tim no. 4). Kalau endpoint mati, bot tetap menyimpan voice note dan bisa diproses ulang nanti.
- Jangan commit API key ke repo.
