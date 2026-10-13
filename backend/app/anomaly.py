import json
import time
from collections import deque

FEATURES = ("current_a", "vib_rms", "temp_c")


class Scorer:
    def __init__(self, window=10, z_alert=3.0, z_clear=2.0, confirm=5, z_max=6.0):
        self.window, self.z_alert, self.z_clear = window, z_alert, z_clear
        self.confirm, self.z_max = confirm, z_max
        self.baselines, self.loaded_at = {}, 0.0
        self.buf, self.hits, self.active = {}, {}, {}

    async def maybe_reload(self, c):
        if time.monotonic() - self.loaded_at < 60:
            return
        rows = await c.fetch("SELECT machine_id, stats FROM baselines")
        self.baselines = {r["machine_id"]: json.loads(r["stats"]) for r in rows}
        self.loaded_at = time.monotonic()

    def reset(self, mid):
        """Dipanggil saat mesin berhenti. Mengembalikan True kalau sebelumnya sedang anomali."""
        self.buf.pop(mid, None)
        self.hits[mid] = 0
        return self.active.pop(mid, False)

    def update(self, mid, data):
        b = self.baselines.get(mid)
        if not b:
            return None
        buf = self.buf.setdefault(mid, deque(maxlen=self.window))
        buf.append({f: float(data.get(f) or 0) for f in FEATURES})
        if len(buf) < self.window:
            return None

        means, z = {}, {}
        for f in FEATURES:
            mean = sum(x[f] for x in buf) / len(buf)
            means[f] = round(mean, 3)
            z[f] = round(abs(mean - b[f]["median"]) / b[f]["scale"], 2)
        zmax = max(z.values())

        was = self.active.get(mid, False)
        if was:
            now = zmax >= self.z_clear
        else:
            self.hits[mid] = self.hits.get(mid, 0) + 1 if zmax >= self.z_alert else 0
            now = self.hits[mid] >= self.confirm
        self.active[mid] = now

        return {
            "score": round(min(zmax / self.z_max, 1.0), 3),
            "z": z,
            "mean": means,
            "base": b,
            "anomaly": now,
            "started": now and not was,
            "ended": was and not now,
        }
