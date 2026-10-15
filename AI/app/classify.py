"""POST /classify - alasan downtime (teks bahasa Indonesia) -> 7 kategori + keyakinan.

Bila LLM gagal, endpoint SENGAJA mengembalikan error (502), bukan tebakan kata kunci:
backend sudah punya fallback kata kunci sendiri (backend/app/ai.py) dan mencatat panggilan
gagal di ai_calls, sehingga halaman "Running on AMD" tidak menghitung hasil palsu sebagai AI.
"""
import json
import logging
import time

from .config import Settings
from .llm import TokenFactoryClient, UpstreamError, extract_json, make_usage
from .schemas import CATEGORIES, ClassifyIn, ClassifyOut

log = logging.getLogger("ai.classify")

SYSTEM_PROMPT = f"""Kamu adalah klasifikator alasan downtime mesin pabrik.
Operator menjawab (teks atau hasil transkrip voice note bahasa Indonesia, bisa tidak baku,
berisi salah dengar, logat, atau campuran bahasa daerah) mengapa mesin berhenti.

Pilih TEPAT SATU kategori dari daftar berikut (tulis persis sama, termasuk tanda hubung panjang "–"):
{json.dumps(CATEGORIES, ensure_ascii=False)}

Panduan:
- "Breakdown – Mekanik": bearing, bunyi kasar, macet, patah, belt/sabuk putus, kopling, gearbox, as, oli bocor, seal bocor.
- "Breakdown – Listrik": MCB/sekring trip, korsleting, kabel, kontaktor, inverter, tidak ada daya, mati lampu/PLN.
- "Breakdown – Overheat": panas berlebih, terbakar, bau gosong, asap, suhu tinggi, thermal trip.
- "Ganti produk/setup": ganti produk/cetakan/mold/ukuran, setting, kalibrasi, changeover.
- "Tunggu material": bahan baku/material habis atau belum datang, menunggu pasokan dari gudang.
- "Istirahat/terjadwal": istirahat, makan, ibadah, pergantian shift, briefing, perawatan rutin terjadwal.
- "Lainnya": tidak jelas, tidak ada kategori yang cocok, atau tidak berkaitan dengan mesin berhenti.
Bila ucapan memuat beberapa alasan, pilih penyebab utama berhentinya mesin (contoh: "motor panas, nunggu teknisi" -> Overheat).
Bila ambigu atau terlalu pendek, pilih kategori terdekat dengan keyakinan rendah (< 0.5).
Jika ada data sensor di konteks, pakai hanya sebagai petunjuk tambahan, bukan pengganti ucapan operator.

Balas HANYA JSON valid tanpa teks lain:
{{"category": "<salah satu kategori>", "confidence": <angka 0 sampai 1>, "rationale": "<alasan satu kalimat>"}}"""


def _canonical(category: str) -> str | None:
    """Terima variasi tanda hubung (- atau –) dan huruf besar/kecil; kembalikan nilai kanonik."""
    key = category.replace("–", "-").replace("—", "-").strip().lower()
    return next((c for c in CATEGORIES if c.replace("–", "-").lower() == key), None)


class Classifier:
    def __init__(self, client: TokenFactoryClient, settings: Settings):
        self.client, self.s = client, settings

    async def classify(self, body: ClassifyIn) -> ClassifyOut:
        started = time.monotonic()
        user = f'Ucapan operator: "{body.text.strip()}"'
        if body.machine_id:
            user += f"\nMesin: {body.machine_id}"
        if body.context:
            user += f"\nKonteks sensor: {json.dumps(body.context, ensure_ascii=False)}"

        res = await self.client.chat(
            # Qwen3.8-27B: tepat satu pesan system, di indeks 0
            [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": user}],
            max_tokens=1024,
            reasoning_effort="low",  # "high" ditolak (400) oleh Qwen3.8-27B
            json_mode=True,
            temperature=0.0,
            budget=self.s.classify_budget,
        )
        obj = extract_json(res.content)
        if not obj or "category" not in obj:
            raise UpstreamError(502, f"keluaran model bukan JSON klasifikasi: {res.content[:120]!r}")

        try:
            confidence = float(obj.get("confidence", 0.5))
        except (TypeError, ValueError):
            confidence = 0.5
        category = _canonical(str(obj["category"]))
        if category is None:
            log.warning("kategori tidak dikenal dari model: %r -> Lainnya", obj["category"])
            category, confidence = "Lainnya", min(confidence, 0.3)

        return ClassifyOut(
            category=category,
            confidence=round(max(0.0, min(1.0, confidence)), 3),
            rationale=str(obj.get("rationale", ""))[:300],
            usage=make_usage(self.s, self.s.analysis_model, started, res.usage),
        )
