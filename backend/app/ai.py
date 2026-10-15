"""Klien AI: /transcribe dan /classify di AMD, dengan mode mock + fallback kata kunci."""
import os
import time

import httpx

CATEGORIES = [
    "Breakdown – Mekanik",
    "Breakdown – Listrik",
    "Breakdown – Overheat",
    "Ganti produk/setup",
    "Tunggu material",
    "Istirahat/terjadwal",
    "Lainnya",
]
REVIEW_CATEGORY = "Perlu dicek"

# Urutan penting: yang lebih spesifik di atas
RULES = [
    ("Breakdown – Overheat", ["panas", "overheat", "asap", "gosong"]),
    ("Breakdown – Listrik", ["listrik", "mcb", "trip", "korslet", "konslet", "pln", "kabel", "sekring", "tegangan", "mati lampu"]),
    ("Tunggu material", ["material", "bahan", "stok", "gudang", "supply"]),
    ("Ganti produk/setup", ["ganti", "mold", "setup", "set up", "cetakan", "changeover", "produk"]),
    ("Istirahat/terjadwal", ["istirahat", "makan", "shift", "jadwal", "sholat", "solat", "briefing", "rutin"]),
    ("Breakdown – Mekanik", ["bearing", "macet", "rusak", "patah", "aus", "bunyi", "getar", "belt", "oli", "bocor", "seret"]),
]


def _base():
    return os.getenv("AI_BASE_URL", "").rstrip("/")


def _headers():
    key = os.getenv("AI_API_KEY", "")
    return {"Authorization": f"Bearer {key}"} if key else {}


def review_below():
    return float(os.getenv("CLASSIFY_REVIEW_BELOW", "0.6"))


def is_mock():
    return not _base()


async def _log(pool, endpoint, started, ok, usage=None, mock=False, error=None):
    u = usage or {}
    latency = u.get("latency_ms") or int((time.monotonic() - started) * 1000)
    try:
        await pool.execute(
            """INSERT INTO ai_calls (endpoint, model, latency_ms, prompt_tokens, completion_tokens, ok, mock, error)
               VALUES ($1,$2,$3,$4,$5,$6,$7,$8)""",
            endpoint, u.get("model") or ("keyword-rules" if mock else None), latency,
            u.get("prompt_tokens"), u.get("completion_tokens"), ok, mock, (error or "")[:500] or None,
        )
    except Exception as e:
        print("Gagal mencatat ai_calls:", e)


def classify_rules(text):
    t = (text or "").lower()
    for cat, words in RULES:
        if any(w in t for w in words):
            return {"category": cat, "confidence": 0.7, "source": "rules"}
    return {"category": "Lainnya", "confidence": 0.3, "source": "rules"}


async def transcribe(pool, path):
    """Mengembalikan {"text": ..., "source": "amd"|"mock"} atau None kalau gagal."""
    started = time.monotonic()
    if is_mock():
        await _log(pool, "transcribe", started, True, mock=True, usage={"model": "mock"})
        return {"text": "[mock] motor panas, nunggu teknisi", "source": "mock"}
    try:
        async with httpx.AsyncClient(timeout=30) as c:
            with open(path, "rb") as f:
                r = await c.post(f"{_base()}/transcribe", headers=_headers(),
                                 files={"file": (os.path.basename(path), f, "audio/ogg")})
        r.raise_for_status()
        data = r.json()
        await _log(pool, "transcribe", started, True, usage=data.get("usage"))
        return {"text": data.get("text", "").strip(), "source": "amd"}
    except Exception as e:
        await _log(pool, "transcribe", started, False, error=str(e))
        print("Transcribe gagal:", e)
        return None


async def classify(pool, text, machine_id):
    """Mengembalikan {"category", "confidence", "source"}. Tidak pernah gagal: fallback ke kata kunci."""
    started = time.monotonic()
    if is_mock():
        result = classify_rules(text)
        await _log(pool, "classify", started, True, mock=True)
        return result
    try:
        async with httpx.AsyncClient(timeout=30) as c:
            r = await c.post(f"{_base()}/classify", headers=_headers(),
                             json={"text": text, "machine_id": machine_id})
        r.raise_for_status()
        data = r.json()
        await _log(pool, "classify", started, True, usage=data.get("usage"))
        cat = data.get("category")
        if cat not in CATEGORIES:
            print(f"Kategori tidak dikenal dari AI: {cat!r}, dianggap Lainnya")
            return {"category": "Lainnya", "confidence": 0.0, "source": "amd"}
        return {"category": cat, "confidence": float(data.get("confidence") or 0), "source": "amd"}
    except Exception as e:
        await _log(pool, "classify", started, False, error=str(e))
        print("Classify AMD gagal, pakai kata kunci:", e)
        return classify_rules(text)


async def explain(pool, payload):
    """POST /explain -> dict (summary, actions, urgency, sources, usage) atau None (mock / gagal)."""
    if is_mock():
        return None
    started = time.monotonic()
    try:
        async with httpx.AsyncClient(timeout=70) as c:
            r = await c.post(f"{_base()}/explain", headers=_headers(), json=payload)
        r.raise_for_status()
        data = r.json()
        await _log(pool, "explain", started, True, usage=data.get("usage"))
        return data
    except Exception as e:
        await _log(pool, "explain", started, False, error=str(e))
        print("Explain gagal:", e)
        return None
