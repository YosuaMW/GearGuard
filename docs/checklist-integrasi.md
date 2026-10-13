# Checklist Integrasi Antar-Peran

Hal yang perlu disepakati supaya backend (peran 2) bisa tersambung dengan peran 1, 3, dan 4. Detail format ada di dokumen tiap peran. Cukup jawab **"oke"** kalau usulan cocok, atau usulkan perubahan.

Dibahas di standup **Selasa 13 Okt, 21.00 WIB**.

| Topik | Peran | Prioritas | Deadline |
|---|---|---|---|
| `/transcribe` + `/classify` | 3 | 🔴 Wajib | Selasa malam |
| `/explain` | 3 | 🟡 Penting | Rabu |
| `types.ts`, rentang waktu, URL Vercel | 4 | 🟡 Penting | Rabu |
| `/score` | 1 | 🟢 Opsional | Kamis |
| Fitur getaran tambahan | 1 | 🟢 Opsional | Kamis |

---

## 🔴 1. `/transcribe` + `/classify` · peran 3 · Selasa malam

Disambungkan **Rabu**: voice note operator → teks → kategori downtime. Detail: [peran3-ai.md](peran3-ai.md).

- [ ] **URL endpoint** di AMD + **API key** (kirim lewat DM, bukan grup/repo)
- [ ] **Cara kirim audio:** file `.ogg` dari Telegram apa adanya, `multipart/form-data` field `file`. Atau peran 3 butuh format lain (`.wav`, base64)?
- [ ] **Balasan `/transcribe`:** `{"text": "..."}`
- [ ] **Balasan `/classify`:** `{"category": "...", "confidence": 0.86}`
- [ ] **7 nama kategori persis sama**, termasuk tanda `–` (en dash). Dashboard menghitung Pareto dari teks ini
- [ ] **Batas "Perlu dicek":** confidence < 0.6?
- [ ] **Waktu proses:** total < 10 detik

**Kalau tidak disepakati:** backend dan AI tidak tersambung, padahal checkpoint Rabu = *"voice note muncul sebagai kategori di dashboard"*.

## 🟡 2. `/explain` · peran 3 · paling lambat Rabu

Dipakai **Kamis**: peringatan anomali → penjelasan LLM + sumber dari manual.

- [ ] **Data yang dikirim backend:** mesin, skor, nilai tiap sensor vs normal, riwayat kerusakan terakhir. Cukup, atau butuh data lain?
- [ ] **Balasan:** `summary`, `actions`, `urgency`, `sources` (judul manual + halaman)
- [ ] **Bahasa:** Inggris, menyesuaikan bot Telegram
- [ ] **Manual untuk RAG** (dicari peran 5)
- [ ] **Waktu proses:** < 15 detik
- [ ] **Field `usage`** (model, latensi, token) di setiap balasan, untuk halaman "Running on AMD"

**Kalau tidak disepakati:** alert tetap terkirim dengan penjelasan berbasis aturan, tapi syarat MVP *"alert dijelaskan LLM dengan sumber manual"* belum terpenuhi.

## 🟡 3. Dashboard · peran 4 · Rabu

Detail: [peran4-frontend.md](peran4-frontend.md).

- [ ] Isi `src/lib/types.ts` untuk `/events`, `/alerts`, `/availability`, `/pareto`
- [ ] **Rentang waktu** Availability/Pareto: 1 jam / 8 jam / per shift?
- [ ] **URL Vercel** untuk ditambahkan ke CORS

**Kalau tidak disepakati:** dashboard hanya bisa menampilkan `/machines`; grafik Availability dan Pareto belum bisa memakai data asli.

## 🟢 4. `/score` · peran 1 · opsional

Dipakai kalau autoencoder siap (Kamis). Detail: [peran1-hardware.md](peran1-hardware.md#5-kontrak-score-autoencoder).

- [ ] **Lokasi endpoint:** AMD Cloud atau Raspi?
- [ ] **Masukan:** 60 detik terakhir (arus, getaran, suhu)
- [ ] **Balasan:** `{"score": 0–1, "anomaly": true/false}`
- [ ] **Waktu proses:** < 1 detik

**Kalau tidak dibuat:** demo tetap jalan dengan deteksi z-score yang sudah ada; disebut jujur di pitch sesuai rencana cadangan tim.

## 🟢 5. Fitur getaran tambahan · peran 1 · opsional

- [ ] Cukup `vib_rms`, atau model butuh fitur lain (`vib_peak`, nilai FFT)?
- [ ] Kalau ada: nama field di JSON MQTT, supaya kolom database ditambah

**Kalau tidak dibahas:** pakai `vib_rms` saja. Deteksi bearing aus sudah terbukti jalan dengan data itu.

---

## Catatan keputusan standup

| Topik | Keputusan | Oleh | Tanggal |
|---|---|---|---|
| | | | |
