# SiagaMesin · AI service (role 3)

Implementasi kontrak [docs/role3-ai.md](../docs/role3-ai.md). Backend di Raspberry Pi memanggil layanan ini lewat HTTPS
(`AI_BASE_URL` + `AI_API_KEY` di `.env` Pi); layanan ini memanggil **AMD Token Factory**.

| Endpoint | Dipanggil backend? | Model |
|---|---|---|
| `POST /transcribe` | ya (`backend/app/ai.py`) | Whisper di instance AMD, atau fallback MiMo-V2.6-Flash |
| `POST /classify` | ya | Qwen3.8-27B |
| `POST /explain` | **belum**: `ai.py` belum punya fungsinya, lihat "Langkah di sisi backend" | Qwen3.8-27B + RAG |
| `POST /ocr`, `POST /rag/ingest` | admin | MinerU2.5-Pro |
| `POST /analyze-downtime` | belum (ekstra) | Qwen3.8-27B |

## Jalankan

```bash
cd ai
cp .env.example .env          # isi RADEON_API_KEY dan AI_SERVICE_KEY
pip install -r requirements.txt
mkdir -p data/manuals         # taruh 2-3 PDF manual motor/pompa di sini
uvicorn app.main:app --port 8001
# Docker: docker compose up -d --build   (ai/docker-compose.yml, untuk host yang bisa dijangkau Pi)
```
Swagger: `/docs`. Status: `GET /health`, `GET /rag/status`. Saat start, PDF di `data/manuals/` yang belum terindeks
otomatis di-ingest di latar belakang. **Nama file PDF menjadi judul sumber** di dashboard
(`Centrifugal_pump_manual.pdf` → "Centrifugal pump manual"), jadi beri nama yang enak dibaca.

## Kontrak (ringkas; rinci di docs/role3-ai.md)

- Auth: `Authorization: Bearer <AI_SERVICE_KEY>` (nilai yang sama dengan `AI_API_KEY` di `.env` Pi).
- Setiap respons berisi `usage`: `{model, latency_ms, prompt_tokens, completion_tokens, gpu}` → tabel `ai_calls`.
- `/classify` mengembalikan kategori persis 7 nilai (en dash `–`); variasi tanda hubung dinormalkan, nilai lain → `Lainnya`.
- `/explain` memakai request/response bahasa Inggris sesuai dokumen; `sources` hanya berisi sumber yang benar-benar dikutip model.
- **Saat model gagal, layanan mengembalikan 5xx/4xx, bukan tebakan.** Backend lalu memakai fallback kata kunci / penjelasan aturan
  miliknya dan mencatat `ok=false`, sehingga halaman "Running on AMD" tidak menghitung hasil palsu sebagai AI.
- Batas waktu internal (15/25/45 dtk untuk classify/transcribe/explain) lebih pendek dari timeout backend (20/30 dtk).

## Uji

```bash
pip install -r requirements-dev.txt
pytest -q tests                      # unit test
python tests/contract_check.py       # memanggil layanan memakai ../backend/app/ai.py ASLI + Token Factory palsu
```

## Catatan penting

1. **Kuota se-tim**: Token Factory 30 RPM / 8 concurrent per key, dipakai berenam. Klien membatasi diri (`RPM_LIMIT=18`),
   retry hanya 429/502/503 sesuai `Retry-After`, dan gagal cepat bila antrean melewati batas waktu. Jangan load test dengan key tim.
2. **Key Token Factory hanya di layanan ini** (`RADEON_API_KEY`), tidak pernah dikirim ke Pi/backend. Jangan commit `.env`.
3. **Whisper bukan bagian Token Factory.** Isi `WHISPER_BASE_URL` bila Whisper jalan di instance AMD; kosong = fallback MiMo (perlu `ffmpeg`, ada di Dockerfile).
4. **Format `/v1/ocr` belum diuji ke server asli.** Dokumentasi hanya menunjukkan `document_url` berupa URL; kode mengirim data URL base64.
   Bila ditolak, ubah `TokenFactoryClient.ocr`. Mode `OCR_MODE=auto` memakai teks bawaan PDF dan hanya halaman scan yang di-OCR.
5. `seed/repair_history.sample.json` hanya **contoh** (disalin ke `data/` saat pertama jalan). Ganti dengan riwayat nyata atau tambah via `POST /rag/repair-history`.
6. Syarat Token Factory: hanya uji/pengembangan, prompt disimpan ±2 hari, jangan kirim data pribadi/sensitif.
7. Matikan instance GPU yang tidak dipakai (aturan tim #4).

## Langkah di sisi backend (belum dikerjakan; kode peran 2)

`/explain` baru berguna bila backend memanggilnya: tambah `explain()` di `backend/app/ai.py`, panggil setelah `INSERT INTO alerts`
di `worker.py`, simpan `summary`→`alerts.explanation` dan `sources`→`alerts.sources`, lalu kirim ke Telegram.
