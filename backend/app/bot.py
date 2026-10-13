import asyncio
import html
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import asyncpg
import httpx
from dotenv import load_dotenv, find_dotenv

load_dotenv(find_dotenv())

TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]
API = f"https://api.telegram.org/bot{TOKEN}"
VOICE_DIR = Path(__file__).resolve().parents[2] / "data" / "voice"
WIB = ZoneInfo("Asia/Jakarta")
WARN_SCORE = 0.5

HELP = (
    "<b>SiagaMesin Bot</b>\n\n"
    "• When a machine stops, I'll ask why. <b>Reply</b> to that message with text or a voice note.\n"
    "• When a machine shows abnormal signs, I'll send an <b>EARLY WARNING</b>.\n"
    "• /status shows the current condition of all machines."
)

STATUS_SQL = """
SELECT m.machine_id, m.name, m.status, m.anomaly_score,
       t.ts, t.current_a, t.vib_rms, t.temp_c, b.stats,
       e.start_ts AS stopped_since
FROM machines m
LEFT JOIN LATERAL (
    SELECT ts, current_a, vib_rms, temp_c FROM telemetry
    WHERE machine_id = m.machine_id ORDER BY ts DESC LIMIT 1
) t ON true
LEFT JOIN baselines b ON b.machine_id = m.machine_id
LEFT JOIN LATERAL (
    SELECT start_ts FROM events
    WHERE machine_id = m.machine_id AND end_ts IS NULL ORDER BY start_ts DESC LIMIT 1
) e ON true
ORDER BY m.machine_id
"""

ICONS = {"running": "🟢", "warning": "🟡", "anomaly": "🟠", "stopped": "🔴", "offline": "⚪"}


def jam(dt):
    return dt.astimezone(WIB).strftime("%H:%M:%S")


def duration(seconds):
    m, s = divmod(int(seconds), 60)
    h, m = divmod(m, 60)
    if h:
        return f"{h}h {m}m"
    return f"{m}m {s}s" if m else f"{s}s"


def sensor_table(r, b, stopped):
    spec = [("Current A", "current_a", ".2f"), ("Vibration", "vib_rms", ".2f"), ("Temp °C", "temp_c", ".1f")]
    out = [f"{'':<10}{'Now':>6}{'Normal':>8}{'Diff':>7}"]
    for label, key, fmt in spec:
        now = r[key]
        now_s = format(now, fmt) if now is not None else "-"
        if b and now is not None:
            med = b[key]["median"]
            norm_s = format(med, fmt)
            diff_s = "-" if stopped or not med else f"{(now - med) / med * 100:+.0f}%"
        else:
            norm_s, diff_s = "-", "-"
        out.append(f"{label:<10}{now_s:>6}{norm_s:>8}{diff_s:>7}")
    return "<pre>" + html.escape("\n".join(out)) + "</pre>"


async def status_text(pool):
    rows = await pool.fetch(STATUS_SQL)
    now = datetime.now(timezone.utc)
    counts = {k: 0 for k in ICONS}
    blocks = []

    for r in rows:
        name = html.escape(r["name"] or r["machine_id"])
        score = r["anomaly_score"]
        score_s = f"{score:.2f}" if score is not None else "-"
        age = (now - r["ts"]).total_seconds() if r["ts"] else None

        if age is None or age > 30:
            state = "offline"
            line = "Offline · no data yet" if age is None else f"Offline · no data for {duration(age)}"
        elif r["status"] == "stopped":
            state = "stopped"
            if r["stopped_since"]:
                since = r["stopped_since"]
                line = f"Stopped since {jam(since)} ({duration((now - since).total_seconds())})"
            else:
                line = "Stopped"
        elif r["status"] == "anomaly":
            state, line = "anomaly", f"<b>ANOMALY</b> · score {score_s}"
        elif score is not None and score >= WARN_SCORE:
            state, line = "warning", f"Warning · score {score_s} (rising)"
        else:
            state, line = "running", f"Running · score {score_s}"

        counts[state] += 1
        block = f"{ICONS[state]} <b>{name}</b> · {r['machine_id']}\n{line}"
        if state != "offline":
            b = json.loads(r["stats"]) if r["stats"] else None
            block += "\n" + sensor_table(r, b, state == "stopped")
        blocks.append(block)

    summary = " · ".join(f"{ICONS[k]} {v} {k}" for k, v in counts.items() if v)
    header = f"📊 <b>Machine Status</b>\n<i>{jam(now)} WIB</i>\n{summary}"
    return "\n\n".join([header] + blocks)


async def send(c, chat_id, text, reply_to=None):
    body = {"chat_id": chat_id, "text": text, "parse_mode": "HTML"}
    if reply_to:
        body["reply_parameters"] = {"message_id": reply_to}
    await c.post(f"{API}/sendMessage", json=body)


async def download_voice(c, file_id, event_id):
    r = await c.get(f"{API}/getFile", params={"file_id": file_id})
    path = r.json()["result"]["file_path"]
    data = await c.get(f"https://api.telegram.org/file/bot{TOKEN}/{path}")
    VOICE_DIR.mkdir(parents=True, exist_ok=True)
    f = VOICE_DIR / f"event_{event_id}.ogg"
    f.write_bytes(data.content)
    return f


async def handle(pool, c, msg):
    chat_id = msg["chat"]["id"]
    if str(chat_id) != CHAT_ID:
        return  # abaikan chat dari orang yang tidak terdaftar

    text = msg.get("text", "")
    if text.startswith("/status"):
        await send(c, chat_id, await status_text(pool))
        return
    if text.startswith("/start") or text.startswith("/help"):
        await send(c, chat_id, HELP)
        return

    reply = msg.get("reply_to_message")
    if not reply:
        await send(c, chat_id, "Please <b>reply</b> to the machine-stopped question so your answer is linked to the right event.\nType /status to see all machines.")
        return

    ev = await pool.fetchrow("SELECT id FROM events WHERE tg_message_id = $1", reply["message_id"])
    if not ev:
        await send(c, chat_id, "That message isn't a machine-stopped question.")
        return

    if "text" in msg:
        await pool.execute("UPDATE events SET transcript = $1 WHERE id = $2", msg["text"], ev["id"])
        await send(c, chat_id, f"✅ Answer saved for event #{ev['id']}\n<i>{html.escape(msg['text'])}</i>", msg["message_id"])
        print(f"[JAWABAN] event {ev['id']}: {msg['text']}")
    elif "voice" in msg:
        f = await download_voice(c, msg["voice"]["file_id"], ev["id"])
        await pool.execute("UPDATE events SET voice_path = $1 WHERE id = $2", str(f), ev["id"])
        await send(c, chat_id, f"🎙️ Voice note received for event #{ev['id']}. Processing…", msg["message_id"])
        print(f"[VOICE] event {ev['id']} disimpan di {f}")
    else:
        await send(c, chat_id, "Please answer with text or a voice note.")


async def main():
    pool = await asyncpg.create_pool(os.environ["DATABASE_URL"], min_size=1, max_size=3)
    offset = None
    async with httpx.AsyncClient(timeout=40) as c:
        await c.post(f"{API}/setMyCommands", json={"commands": [
            {"command": "status", "description": "Current condition of all machines"},
            {"command": "help", "description": "How to use this bot"},
        ]})
        print("Bot siap menerima jawaban...")
        while True:
            try:
                params = {"timeout": 30}
                if offset:
                    params["offset"] = offset
                r = await c.get(f"{API}/getUpdates", params=params)
                for u in r.json().get("result", []):
                    offset = u["update_id"] + 1
                    if "message" in u:
                        try:
                            await handle(pool, c, u["message"])
                        except Exception as e:
                            print("Gagal proses pesan:", e)
            except httpx.HTTPError as e:
                print("Koneksi Telegram error, coba lagi:", e)
                await asyncio.sleep(3)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Bot dihentikan")
