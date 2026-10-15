"""Angka untuk slide pitch, dihitung dari database.

  docker compose exec worker python /app/tools/metrics.py --hours 24
  docker compose exec worker python /app/tools/metrics.py --hours 24 --live-only
"""
import argparse
import asyncio
import os
import statistics

import asyncpg

BREAKDOWN = ("Breakdown – Mekanik", "Breakdown – Listrik", "Breakdown – Overheat")
LEAD_WINDOW_MIN = 15   # alert dianggap memprediksi kalau mesin berhenti dalam 15 menit
LOOKBACK_MIN = 5       # breakdown dianggap terprediksi kalau ada alert dalam 5 menit sebelumnya


def pct(a, b):
    return f"{a / b * 100:.0f}%" if b else "-"


async def main(hours, live_only):
    c = await asyncpg.connect(os.environ["DATABASE_URL"])
    src = "AND m.source = 'live'" if live_only else ""
    since = f"now() - make_interval(hours => {int(hours)})"

    ev = await c.fetchrow(f"""
        SELECT count(*) AS stops,
               count(*) FILTER (WHERE e.category IS NOT NULL) AS with_reason,
               count(*) FILTER (WHERE e.needs_review) AS review,
               count(*) FILTER (WHERE e.voice_path IS NOT NULL) AS voice,
               coalesce(sum(extract(epoch FROM coalesce(e.end_ts, now()) - e.start_ts)), 0) / 60 AS minutes
        FROM events e JOIN machines m USING (machine_id)
        WHERE e.start_ts > {since} {src}""")

    leads = await c.fetch(f"""
        SELECT a.id, a.machine_id, x.category,
               extract(epoch FROM x.start_ts - a.ts) AS lead_s
        FROM alerts a JOIN machines m USING (machine_id)
        LEFT JOIN LATERAL (
            SELECT start_ts, category FROM events
            WHERE machine_id = a.machine_id AND start_ts >= a.ts
              AND start_ts < a.ts + make_interval(mins => {LEAD_WINDOW_MIN})
            ORDER BY start_ts LIMIT 1) x ON true
        WHERE a.ts > {since} {src}""")

    recall = await c.fetchrow(f"""
        SELECT count(*) AS breakdowns,
               count(*) FILTER (WHERE EXISTS (
                   SELECT 1 FROM alerts a WHERE a.machine_id = e.machine_id
                     AND a.ts <= e.start_ts AND a.ts > e.start_ts - make_interval(mins => {LOOKBACK_MIN}))) AS predicted
        FROM events e JOIN machines m USING (machine_id)
        WHERE e.start_ts > {since} AND e.category = 'Breakdown – Mekanik' {src}""")

    all_bd = await c.fetchval(f"""
        SELECT count(*) FROM events e JOIN machines m USING (machine_id)
        WHERE e.start_ts > {since} AND e.category = ANY($1::text[]) {src}""", list(BREAKDOWN))
    await c.close()

    scope = "live machines only" if live_only else "all machines (live rig + replay simulator)"
    print(f"\n=== GearGuard metrics · last {hours} h · {scope} ===\n")

    print("DOWNTIME LOGGING")
    print(f"  Stops detected automatically : {ev['stops']}")
    print(f"  Stops with a reason          : {ev['with_reason']} ({pct(ev['with_reason'], ev['stops'])})")
    print(f"  Needs review (low confidence): {ev['review']} ({pct(ev['review'], ev['stops'])})")
    print(f"  Answered by voice note       : {ev['voice']}")
    print(f"  Total downtime logged        : {float(ev['minutes']):.0f} min\n")

    hits = [float(r["lead_s"]) for r in leads if r["lead_s"] is not None and r["category"] in BREAKDOWN]
    print("EARLY WARNING")
    print(f"  Alerts raised                : {len(leads)}")
    print(f"  Followed by a breakdown      : {len(hits)} ({pct(len(hits), len(leads))}) within {LEAD_WINDOW_MIN} min")
    if hits:
        print(f"  Lead time before stop        : median {statistics.median(hits):.0f} s "
              f"(min {min(hits):.0f} s, max {max(hits):.0f} s)")
    print(f"  Mechanical breakdowns        : {recall['breakdowns']}")
    print(f"  ...warned in advance         : {recall['predicted']} ({pct(recall['predicted'], recall['breakdowns'])})")
    print(f"  All breakdowns (mech/elec/heat): {all_bd}\n")

    print("Note: replay machines use simulated data; say so on the slide.")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--hours", type=float, default=24)
    p.add_argument("--live-only", action="store_true", help="hanya mesin live (rig asli)")
    a = p.parse_args()
    asyncio.run(main(a.hours, a.live_only))
