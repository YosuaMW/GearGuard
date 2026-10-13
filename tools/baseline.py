import argparse
import asyncio
import json
import os
import statistics

import asyncpg
from dotenv import load_dotenv, find_dotenv

load_dotenv(find_dotenv())

FEATURES = ("current_a", "vib_rms", "temp_c")
STOP_A = float(os.getenv("STOP_CURRENT_A", "0.3"))


async def main(minutes):
    conn = await asyncpg.connect(os.environ["DATABASE_URL"])
    mids = [r["machine_id"] for r in await conn.fetch("SELECT machine_id FROM machines ORDER BY machine_id")]

    for mid in mids:
        rows = await conn.fetch(
            """SELECT current_a, vib_rms, temp_c FROM telemetry
               WHERE machine_id = $1 AND current_a >= $2
               AND ts > now() - make_interval(mins => $3)""",
            mid, STOP_A, minutes,
        )
        if len(rows) < 60:
            print(f"{mid}: data jalan baru {len(rows)} baris, minimal 60. Dilewati.")
            continue

        stats = {}
        for f in FEATURES:
            vals = [float(r[f]) for r in rows if r[f] is not None]
            med = statistics.median(vals)
            mad = statistics.median(abs(v - med) for v in vals)
            scale = max(1.4826 * mad, 0.02 * abs(med), 1e-3)
            stats[f] = {"median": round(med, 4), "scale": round(scale, 4)}

        await conn.execute(
            """INSERT INTO baselines (machine_id, stats, computed_at) VALUES ($1, $2, now())
               ON CONFLICT (machine_id) DO UPDATE SET stats = EXCLUDED.stats, computed_at = now()""",
            mid, json.dumps(stats),
        )
        print(f"{mid}: {len(rows)} baris -> {stats}")

    await conn.close()


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--minutes", type=int, default=30, help="ambil data jalan normal N menit terakhir")
    asyncio.run(main(p.parse_args().minutes))
