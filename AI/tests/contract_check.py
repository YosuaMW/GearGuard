"""Uji kontrak: layanan AI dipanggil memakai backend/app/ai.py ASLI (klien yang jalan di Raspberry Pi).

    python tests/contract_check.py

Menjalankan Token Factory palsu (:9001) + layanan AI (:8001), tanpa memakai kuota API asli.
"""
import asyncio
import importlib.util
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import httpx

AI_DIR = Path(__file__).resolve().parent.parent
BACKEND_AI = AI_DIR.parent / "backend" / "app" / "ai.py"
UP, SVC, KEY = 9001, 8001, "testkey"
failures: list[str] = []


def check(name: str, cond: bool, extra: str = "") -> None:
    print(("PASS " if cond else "FAIL ") + name + (f"  [{extra}]" if extra else ""))
    if not cond:
        failures.append(name)


class FakePool:
    def __init__(self):
        self.rows = []

    async def execute(self, sql, *args):
        self.rows.append(args)


def wait_ready(url: str, secs: float = 20) -> None:
    end = time.time() + secs
    while time.time() < end:
        try:
            if httpx.get(url, timeout=1).status_code < 500:
                return
        except httpx.HTTPError:
            time.sleep(0.3)
    raise RuntimeError(f"{url} tidak siap")


def load_backend_ai():
    spec = importlib.util.spec_from_file_location("backend_ai", BACKEND_AI)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


async def main(tmp: str) -> None:
    ai = load_backend_ai()
    pool = FakePool()
    voice = Path(tmp) / "event_1.ogg"
    voice.write_bytes(b"OggS-fake-audio")

    os.environ.update(AI_BASE_URL=f"http://127.0.0.1:{SVC}", AI_API_KEY=KEY)
    tr = await ai.transcribe(pool, str(voice))
    check("backend transcribe() -> source amd + teks", bool(tr) and tr["source"] == "amd" and "panas" in tr["text"], str(tr))

    cl = await ai.classify(pool, "motor panas, nunggu teknisi", "m1")
    check("backend classify() -> kategori en dash persis + source amd",
          cl["category"] == "Breakdown – Overheat" and cl["source"] == "amd" and cl["confidence"] > 0.8, str(cl))

    ok_rows = [r for r in pool.rows if r[5] is True]  # kolom ok
    check("ai_calls mencatat model + latency + token dari field usage",
          len(ok_rows) == 2 and all(r[1] and r[2] is not None for r in ok_rows) and ok_rows[1][3] == 50, str(pool.rows))

    payload = {
        "alert_id": 4, "machine_id": "m2", "machine_name": "Pump", "ts": "2026-10-14T09:24:25Z", "score": 0.80,
        "features": {"vib_rms": {"now": 0.55, "normal": 0.40, "z": 4.75}, "temp_c": {"now": 46.6, "normal": 45.3, "z": 2.09},
                     "current_a": {"now": 2.33, "normal": 2.30, "z": 1.03}},
        "recent_events": [{"ts": "2026-10-14T09:10:12Z", "category": "Breakdown – Mekanik", "transcript": "seal pompa bocor, diganti dulu"}],
    }
    async with httpx.AsyncClient(timeout=30) as c:
        r = await c.post(f"http://127.0.0.1:{SVC}/explain", json=payload, headers={"Authorization": f"Bearer {KEY}"})
    j = r.json()
    check("/explain 200 + field kontrak (summary, actions, urgency, sources, usage)",
          r.status_code == 200 and all(k in j for k in ("summary", "actions", "urgency", "sources", "usage")), r.text[:200])
    check("/explain sumber berformat {title, page, snippet}",
          not j["sources"] or all({"title", "page", "snippet"} <= set(s) for s in j["sources"]), str(j.get("sources"))[:200])

    os.environ["AI_API_KEY"] = "kunci-salah"
    cl = await ai.classify(pool, "material belum datang", "m1")
    check("kunci salah -> 401 -> backend jatuh ke kata kunci (source rules), dicatat ok=False",
          cl["source"] == "rules" and pool.rows[-1][5] is False, str(cl))
    os.environ["AI_API_KEY"] = KEY

    os.environ["AI_BASE_URL"] = "http://127.0.0.1:9"  # tidak ada server
    cl = await ai.classify(pool, "material belum datang", "m1")
    check("layanan AI mati -> backend tetap jalan lewat kata kunci", cl["category"] == "Tunggu material" and cl["source"] == "rules")


if __name__ == "__main__":
    if not BACKEND_AI.exists():
        sys.exit(f"{BACKEND_AI} tidak ditemukan; jalankan dari dalam repo SiagaMesin")
    tmp = tempfile.mkdtemp()
    env = {**os.environ, "RADEON_BASE_URL": f"http://127.0.0.1:{UP}/v1", "RADEON_API_KEY": "rc-test",
           "AI_SERVICE_KEY": KEY, "WHISPER_BASE_URL": f"http://127.0.0.1:{UP}/v1", "DATA_DIR": tmp,
           "MANUALS_DIR": f"{tmp}/manuals", "REPAIR_HISTORY_FILE": f"{tmp}/repair.json", "RPM_LIMIT": "1000"}
    procs = [
        subprocess.Popen([sys.executable, "-m", "uvicorn", "tests.mock_upstream:app", "--port", str(UP), "--log-level", "warning"], cwd=AI_DIR, env=env),
        subprocess.Popen([sys.executable, "-m", "uvicorn", "app.main:app", "--port", str(SVC), "--log-level", "warning"], cwd=AI_DIR, env=env),
    ]
    try:
        wait_ready(f"http://127.0.0.1:{UP}/docs")
        wait_ready(f"http://127.0.0.1:{SVC}/health")
        asyncio.run(main(tmp))
    finally:
        for p in procs:
            p.terminate()
    print("\nSEMUA LOLOS" if not failures else f"\nGAGAL: {failures}")
    sys.exit(1 if failures else 0)
