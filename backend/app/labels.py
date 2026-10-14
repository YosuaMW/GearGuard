"""Label kategori (bahasa Inggris untuk dashboard & bot) dan perhitungan rentang waktu shift."""
import os
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

WIB = ZoneInfo("Asia/Jakarta")

# kategori di database (kontrak dengan peran 3) -> (id stabil, label tampilan)
CATEGORIES = {
    "Breakdown – Mekanik": ("mechanical", "Breakdown – Mechanical"),
    "Breakdown – Listrik": ("electrical", "Breakdown – Electrical"),
    "Breakdown – Overheat": ("overheat", "Breakdown – Overheat"),
    "Ganti produk/setup": ("changeover", "Changeover / setup"),
    "Tunggu material": ("material", "Waiting for material"),
    "Istirahat/terjadwal": ("break", "Break / scheduled"),
    "Lainnya": ("other", "Other"),
    "Perlu dicek": ("review", "Needs review"),
}
PLANNED = {"Istirahat/terjadwal"}   # tidak dihitung mengurangi availability


def category_id(c):
    return CATEGORIES.get(c, ("other", c))[0] if c else None


def label(c):
    return CATEGORIES.get(c, (None, c))[1] if c else None


def _shift_starts():
    out = []
    for part in os.getenv("SHIFT_STARTS", "06:00,14:00,22:00").split(","):
        h, m = part.strip().split(":")
        out.append((int(h), int(m)))
    return sorted(out)


def shift_bounds(now=None):
    """Mengembalikan (mulai, selesai, nomor_shift) untuk shift yang sedang berjalan."""
    now = (now or datetime.now(timezone.utc)).astimezone(WIB)
    starts = _shift_starts()
    cands = []
    for d in (-1, 0, 1):
        day = (now + timedelta(days=d)).date()
        for i, (h, m) in enumerate(starts):
            cands.append((datetime(day.year, day.month, day.day, h, m, tzinfo=WIB), i + 1))
    cands.sort()
    for k in range(len(cands) - 1):
        if cands[k][0] <= now < cands[k + 1][0]:
            return cands[k][0], cands[k + 1][0], cands[k][1]
    raise RuntimeError("shift tidak ditemukan")


RANGES = ("shift", "today", "1h", "8h", "24h")


def range_bounds(name="shift", now=None):
    now = now or datetime.now(timezone.utc)
    local = now.astimezone(WIB)
    if name == "shift":
        start, end, no = shift_bounds(now)
        return {"range": name, "start": start, "end": now, "shift_end": end,
                "label": f"Shift {no} · {start:%H:%M}–{end:%H:%M}"}
    if name == "today":
        start = local.replace(hour=0, minute=0, second=0, microsecond=0)
        return {"range": name, "start": start, "end": now, "shift_end": None, "label": "Today"}
    hours = {"1h": 1, "8h": 8, "24h": 24}[name]
    return {"range": name, "start": now - timedelta(hours=hours), "end": now, "shift_end": None,
            "label": f"Last {hours} h"}
