import asyncio
import json
import os
from datetime import datetime, timezone

import aiomqtt
import asyncpg
from dotenv import load_dotenv, find_dotenv

from app.anomaly import Scorer
from app import db
from app.notify import ask_reason, send_alert, send_resolved

load_dotenv(find_dotenv())

MQTT_HOST = os.getenv("MQTT_HOST", "localhost")
STOP_A = float(os.getenv("STOP_CURRENT_A", "0.3"))
STOP_SEC = int(os.getenv("STOP_SECONDS", "5"))
GAP_S = int(os.getenv("DATA_GAP_SECONDS", "30"))   # data putus lebih lama dari ini = event ditutup
NOTIFY_SOURCES = set(os.getenv("ALERT_NOTIFY_SOURCES", "live,replay").split(","))

state = {}
last_ts = {}
scorer = Scorer(
    window=int(os.getenv("ANOMALY_WINDOW_S", "10")),
    z_alert=float(os.getenv("ANOMALY_Z_ALERT", "3")),
    z_clear=float(os.getenv("ANOMALY_Z_CLEAR", "2")),
    confirm=int(os.getenv("ANOMALY_CONFIRM_S", "5")),
)


def parse_ts(s):
    if not s:
        return datetime.now(timezone.utc)
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


async def restore_state(pool):
    """Lanjutkan event & alert yang masih terbuka dari sesi worker sebelumnya."""
    async with pool.acquire() as c:
        rows = await c.fetch(
            """SELECT DISTINCT ON (machine_id) id, machine_id, start_ts FROM events
               WHERE end_ts IS NULL ORDER BY machine_id, start_ts DESC"""
        )
        keep = [r["id"] for r in rows]
        for r in rows:
            state[r["machine_id"]] = {"low_since": r["start_ts"], "stopped": True, "event_id": r["id"]}
        await c.execute(
            "UPDATE events SET end_ts = start_ts WHERE end_ts IS NULL AND NOT (id = ANY($1::int[]))", keep
        )

        for r in await c.fetch("SELECT machine_id, last_seen FROM machines WHERE last_seen IS NOT NULL"):
            last_ts[r["machine_id"]] = r["last_seen"]
        open_alerts = await c.fetch("SELECT DISTINCT machine_id FROM alerts WHERE resolved_ts IS NULL")
        for a in open_alerts:
            scorer.active[a["machine_id"]] = True

    print(f"[START] lanjut {len(rows)} event berhenti, {len(open_alerts)} alert terbuka")


async def machine_name(c, mid):
    return await c.fetchval("SELECT name FROM machines WHERE machine_id = $1", mid) or mid


async def on_stop(c, mid, st, data):
    if data.get("source") == "replay" and data.get("reason_category"):
        await c.execute(
            "UPDATE events SET transcript = $1, category = $2, confidence = 1.0 WHERE id = $3",
            data.get("reason_text"), data["reason_category"], st["event_id"],
        )
        print(f"[OTOMATIS] event {st['event_id']} ({mid}): {data['reason_category']}")
        return

    try:
        msg_id = await ask_reason(await machine_name(c, mid), st["event_id"], st["low_since"])
        if msg_id:
            await c.execute(
                "UPDATE events SET tg_message_id = $1 WHERE id = $2", msg_id, st["event_id"]
            )
            print(f"[TELEGRAM] pertanyaan terkirim untuk event {st['event_id']} ({mid})")
    except Exception as e:
        print("Gagal kirim Telegram:", e)


async def close_alerts(c, mid, ts):
    rows = await c.fetch(
        "UPDATE alerts SET resolved_ts = $1 WHERE machine_id = $2 AND resolved_ts IS NULL RETURNING id",
        ts, mid,
    )
    return [r["id"] for r in rows]


async def notify_alert(c, mid, source, aid, ts, r):
    if source not in NOTIFY_SOURCES:
        return
    try:
        msg_id = await send_alert(await machine_name(c, mid), aid, ts, r)
        if msg_id:
            await c.execute("UPDATE alerts SET tg_message_id = $1 WHERE id = $2", msg_id, aid)
            print(f"[TELEGRAM] alert {aid} terkirim ({mid})")
    except Exception as e:
        print("Gagal kirim alert Telegram:", e)


async def notify_resolved(c, mid, source, ids):
    if not ids or source not in NOTIFY_SOURCES:
        return
    try:
        await send_resolved(await machine_name(c, mid), ids)
    except Exception as e:
        print("Gagal kirim info normal:", e)


async def handle(pool, data):
    mid = data["machine_id"]
    source = data.get("source", "live")
    ts = parse_ts(data.get("ts"))
    cur = float(data.get("current_a") or 0)

    async with pool.acquire() as c:
        await c.execute(
            """INSERT INTO machines (machine_id, name, source) VALUES ($1, $2, $3)
               ON CONFLICT (machine_id) DO UPDATE SET source = EXCLUDED.source""",
            mid, data.get("name") or mid, source,
        )
        await c.execute(
            "INSERT INTO telemetry (ts, machine_id, current_a, vib_rms, temp_c) VALUES ($1,$2,$3,$4,$5)",
            ts, mid, cur, data.get("vib_rms"), data.get("temp_c"),
        )

        # --- deteksi berhenti / jalan ---
        st = state.setdefault(mid, {"low_since": None, "stopped": False, "event_id": None})
        prev = last_ts.get(mid)
        last_ts[mid] = ts
        if prev and (ts - prev).total_seconds() > GAP_S:
            # data sempat putus: tutup event/alert di waktu data terakhir, jangan dihitung berhenti selama putus
            if st["stopped"]:
                await c.execute("UPDATE events SET end_ts = $1 WHERE id = $2", prev, st["event_id"])
                print(f"[DATA PUTUS] {mid} event {st['event_id']} ditutup di {prev:%H:%M:%S}")
            st.update(low_since=None, stopped=False, event_id=None)
            if scorer.reset(mid):
                await c.execute("UPDATE alerts SET resolved_ts = $1 WHERE machine_id = $2 AND resolved_ts IS NULL", prev, mid)
        if cur < STOP_A:
            st["low_since"] = st["low_since"] or ts
            if not st["stopped"] and (ts - st["low_since"]).total_seconds() >= STOP_SEC:
                st["stopped"] = True
                st["event_id"] = await c.fetchval(
                    "INSERT INTO events (machine_id, start_ts) VALUES ($1, $2) RETURNING id",
                    mid, st["low_since"],
                )
                print(f"[BERHENTI] {mid} (event {st['event_id']})")
                await on_stop(c, mid, st, data)
        else:
            if st["stopped"]:
                await c.execute("UPDATE events SET end_ts = $1 WHERE id = $2", ts, st["event_id"])
                print(f"[JALAN] {mid} jalan lagi, event {st['event_id']} ditutup")
            st.update(low_since=None, stopped=False, event_id=None)

        # --- deteksi anomali ---
        await scorer.maybe_reload(c)
        score, anomaly = None, False
        if cur < STOP_A:
            if scorer.reset(mid):
                await close_alerts(c, mid, ts)
                print(f"[ALERT DITUTUP] {mid} berhenti")
        else:
            r = scorer.update(mid, data)
            if r:
                score, anomaly = r["score"], r["anomaly"]
                if r["started"]:
                    aid = await c.fetchval(
                        "INSERT INTO alerts (machine_id, ts, score, features) VALUES ($1,$2,$3,$4) RETURNING id",
                        mid, ts, score, json.dumps({f: {"now": r["mean"][f], "normal": r["base"][f]["median"], "z": r["z"][f]} for f in r["z"]}),
                    )
                    print(f"[ANOMALI] {mid} alert {aid}, z={r['z']}")
                    await notify_alert(c, mid, source, aid, ts, r)
                elif anomaly:
                    await c.execute(
                        """UPDATE alerts SET score = GREATEST(score, $1), features = $2
                           WHERE machine_id = $3 AND resolved_ts IS NULL""",
                        score, json.dumps({f: {"now": r["mean"][f], "normal": r["base"][f]["median"], "z": r["z"][f]} for f in r["z"]}), mid,
                    )
                elif r["ended"]:
                    ids = await close_alerts(c, mid, ts)
                    print(f"[NORMAL] {mid} kembali normal")
                    await notify_resolved(c, mid, source, ids)
            elif scorer.active.get(mid):
                anomaly = True  # alert lama masih terbuka, tunggu buffer terisi

        status = "stopped" if st["stopped"] else ("anomaly" if anomaly else "running")
        await c.execute(
            """UPDATE machines SET status = $1, last_seen = $2,
               anomaly_score = COALESCE($3, anomaly_score) WHERE machine_id = $4""",
            status, ts, score, mid,
        )


async def main():
    pool = await db.create_pool(max_size=3)
    await restore_state(pool)
    while True:
        try:
            async with aiomqtt.Client(MQTT_HOST) as client:
                await client.subscribe("siagamesin/+/telemetry")
                print("Worker terhubung ke MQTT, menunggu data...")
                async for msg in client.messages:
                    try:
                        await handle(pool, json.loads(msg.payload))
                    except Exception as e:
                        print("Data dilewati:", e)
        except aiomqtt.MqttError as e:
            print("MQTT putus, coba lagi 3 detik:", e)
            await asyncio.sleep(3)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Worker dihentikan")
