import html
import os
from zoneinfo import ZoneInfo

import httpx

WIB = ZoneInfo("Asia/Jakarta")
LABELS = {"current_a": ("Current", "A"), "vib_rms": ("Vibration", ""), "temp_c": ("Temperature", "°C")}


async def _send(text, force_reply=False, reply_to=None):
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat = os.getenv("TELEGRAM_CHAT_ID")
    if not token or not chat:
        print("Telegram belum diatur, pesan tidak dikirim")
        return None
    body = {"chat_id": chat, "text": text, "parse_mode": "HTML"}
    if force_reply:
        body["reply_markup"] = {"force_reply": True}
    if reply_to:
        body["reply_parameters"] = {"message_id": reply_to, "allow_sending_without_reply": True}
    async with httpx.AsyncClient(timeout=10) as c:
        r = await c.post(f"https://api.telegram.org/bot{token}/sendMessage", json=body)
        r.raise_for_status()
        return r.json()["result"]["message_id"]


async def ask_reason(machine_name, event_id, start_ts):
    jam = start_ts.astimezone(WIB).strftime("%H:%M:%S")
    text = (
        f"⚠️ <b>{html.escape(machine_name)} stopped</b> at {jam} WIB\n\n"
        "Why did it stop? Reply to this message with a voice note or text.\n"
        f"<i>event #{event_id}</i>"
    )
    return await _send(text, force_reply=True)


def _diagnose(r):
    z, mean, base = r["z"], r["mean"], r["base"]
    top = max(z, key=z.get)
    up = mean[top] > base[top]["median"]
    if top == "vib_rms" and up:
        return ("Vibration is above normal, a typical sign of bearing wear, imbalance, or loose mounting bolts.",
                "Check bearing noise and temperature, bolt tightness, and lubrication.")
    if top == "temp_c" and up:
        return ("Motor temperature is rising. The cooling fan or vents may be blocked, or the machine is overloaded.",
                "Check the cooling fan, motor fins, and machine load.")
    if top == "current_a" and up:
        return ("Current is above normal. The motor is working harder due to overload or mechanical friction.",
                "Check the load, shaft alignment, and lubrication.")
    if top == "current_a" and not up:
        return ("Current dropped. The load may be lost, the belt slipping or broken, or the coupling loose.",
                "Check the belt, coupling, and load connection.")
    return ("Sensor pattern deviates from normal.", "Perform a visual inspection of the machine.")


async def send_alert(machine_name, alert_id, ts, r):
    jam = ts.astimezone(WIB).strftime("%H:%M:%S")
    lines = []
    for f in sorted(r["z"], key=r["z"].get, reverse=True):
        label, unit = LABELS[f]
        z, mean, med = r["z"][f], r["mean"][f], r["base"][f]["median"]
        pct = (mean - med) / med * 100 if med else 0
        icon = "🔴" if z >= 3 else ("🟡" if z >= 2 else "🟢")
        u = f" {unit}" if unit else ""
        lines.append(f"{icon} {label}: <b>{mean:.2f}{u}</b> (normal {med:.2f}, {pct:+.0f}%)")
    cause, action = _diagnose(r)
    text = (
        f"🚨 <b>EARLY WARNING · {html.escape(machine_name)}</b>\n"
        f"Detected at {jam} WIB · anomaly score <b>{r['score']:.2f}</b>\n\n"
        "<b>Last 10 s vs normal</b>\n" + "\n".join(lines) + "\n\n"
        f"<b>Likely cause</b>\n{cause}\n\n"
        f"<b>Recommended action</b>\n{action}\n\n"
        "The machine is still running. Schedule an inspection before it fails.\n"
        f"<i>alert #{alert_id}</i>"
    )
    return await _send(text)


async def send_resolved(machine_name, alert_ids):
    ids = ", ".join(f"#{i}" for i in alert_ids)
    return await _send(f"✅ <b>{html.escape(machine_name)}</b> is back to normal\n<i>alert {ids} closed</i>")


async def send_explanation(machine_name, alert_id, data, reply_to=None):
    acts = "\n".join(f"• {html.escape(str(a))}" for a in (data.get("actions") or [])[:5])
    srcs = []
    for s in (data.get("sources") or [])[:3]:
        t = html.escape(s.get("title") or "source")
        if s.get("page"):
            t += f", p. {s['page']}"
        srcs.append(f"📖 {t}")
    model = (data.get("usage") or {}).get("model") or "AI"
    text = f"🤖 <b>AI analysis · {html.escape(machine_name)}</b>\n\n{html.escape(data.get('summary', ''))}\n"
    if acts:
        text += f"\n<b>Actions</b>\n{acts}\n"
    if data.get("urgency"):
        text += f"\n<b>Urgency:</b> {html.escape(str(data['urgency']))}\n"
    if srcs:
        text += "\n<b>Sources</b>\n" + "\n".join(srcs) + "\n"
    text += f"\n<i>alert #{alert_id} · {html.escape(model)} on AMD</i>"
    return await _send(text, reply_to=reply_to)
