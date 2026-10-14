"""Simulator mesin SiagaMesin.

Perintah lewat MQTT (topic siagamesin/sim/cmd), contoh:
  docker compose exec mqtt mosquitto_pub -t siagamesin/sim/cmd -m "wear m2"
    wear <id> [detik]          mulai bearing aus sekarang (default 90 detik lalu berhenti)
    stop <id> [detik] [alasan] berhenti sekarang; alasan: material|setup|break|electrical|overheat|other
    calm                       matikan kejadian acak (semua mesin jalan normal)
    random                     nyalakan lagi kejadian acak
    status                     cetak fase semua mesin di log simulator
"""
import argparse
import asyncio
import json
import os
import random
from datetime import datetime, timezone

import aiomqtt

REPLAY = {
    "m2": {"name": "Pump", "cur": 2.4, "vib": 0.35, "temp": 45},
    "m3": {"name": "Mixer", "cur": 3.1, "vib": 0.28, "temp": 48},
    "m4": {"name": "Compressor", "cur": 1.6, "vib": 0.40, "temp": 40},
}
LIVE_STANDIN = {"m1": {"name": "Conveyor motor", "cur": 1.8, "vib": 0.42, "temp": 41}}

REASONS = {
    "setup": ("Ganti produk/setup", "ganti mold untuk produk B"),
    "material": ("Tunggu material", "material dari gudang belum datang"),
    "break": ("Istirahat/terjadwal", "istirahat shift"),
    "electrical": ("Breakdown – Listrik", "MCB trip, direset teknisi"),
    "overheat": ("Breakdown – Overheat", "motor panas, didinginkan dulu"),
    "other": ("Lainnya", "dicek QC"),
}
WEAR_REASON = ("Breakdown – Mekanik", "bearing aus, diganti teknisi")
CMD_TOPIC = "siagamesin/sim/cmd"


class Machine:
    def __init__(self, mid, cfg, source):
        self.mid, self.cfg, self.source = mid, cfg, source
        self.phase, self.left = "run", random.randint(60, 180)
        self.wear, self.wear_len, self.reason = 0.0, 90, None

    def start_wear(self, seconds=90):
        self.phase, self.left, self.wear, self.wear_len = "wear", seconds, 0.0, seconds

    def start_stop(self, seconds, reason):
        self.phase, self.left, self.reason, self.wear = "stop", seconds, reason, 0.0

    def step(self, random_events):
        self.left -= 1
        if self.phase == "run" and self.left <= 0:
            if not random_events:
                self.left = random.randint(60, 180)
            elif random.random() < 0.3:
                self.start_wear(90)
            else:
                self.start_stop(random.randint(20, 60), random.choice(list(REASONS.values())))
        elif self.phase == "wear":
            self.wear = min(1.0, self.wear + 1 / self.wear_len)
            if self.left <= 0:
                self.start_stop(random.randint(30, 60), WEAR_REASON)
        elif self.phase == "stop" and self.left <= 0:
            self.phase, self.left = "run", random.randint(60, 180)
            self.reason, self.wear = None, 0.0

        c, w = self.cfg, self.wear
        if self.phase == "stop":
            vals = {
                "current_a": round(random.uniform(0, 0.1), 2),
                "vib_rms": 0.01,
                "temp_c": round(c["temp"] - 3 + random.uniform(-0.5, 0.5), 1),
            }
        else:
            vals = {
                "current_a": round(c["cur"] * (1 + 0.15 * w) + random.gauss(0, 0.05), 2),
                "vib_rms": round(c["vib"] * (1 + 2.0 * w) + random.gauss(0, 0.03), 3),
                "temp_c": round(c["temp"] + 8 * w + random.gauss(0, 0.4), 1),
            }

        msg = {
            "machine_id": self.mid,
            "name": c["name"],
            "source": self.source,
            "ts": datetime.now(timezone.utc).isoformat(),
            **vals,
        }
        if self.phase == "stop" and self.source == "replay":
            msg["reason_category"], msg["reason_text"] = self.reason
        return msg


def handle_command(text, machines, state):
    parts = text.strip().split()
    if not parts:
        return "perintah kosong"
    cmd, args = parts[0].lower(), parts[1:]
    if cmd == "calm":
        state["random"] = False
        return "kejadian acak MATI"
    if cmd == "random":
        state["random"] = True
        return "kejadian acak NYALA"
    if cmd == "status":
        return " | ".join(f"{m.mid}:{m.phase}({m.left}s)" for m in machines.values())
    if cmd in ("wear", "stop"):
        if not args or args[0] not in machines:
            return f"mesin tidak dikenal, pilih: {', '.join(machines)}"
        m = machines[args[0]]
        try:
            seconds = int(args[1]) if len(args) > 1 else (90 if cmd == "wear" else 40)
        except ValueError:
            return "detik harus angka"
        if cmd == "wear":
            m.start_wear(max(seconds, 20))
            return f"{m.mid} mulai bearing aus, berhenti dalam {m.left} detik"
        key = args[2] if len(args) > 2 else "other"
        if key not in REASONS:
            return f"alasan tidak dikenal, pilih: {', '.join(REASONS)}"
        m.start_stop(max(seconds, 6), REASONS[key])
        return f"{m.mid} berhenti {m.left} detik ({REASONS[key][0]})"
    return f"perintah tidak dikenal: {cmd}"


async def listen(client, machines, state):
    async for msg in client.messages:
        text = msg.payload.decode(errors="ignore")
        print(f"[PERINTAH] {text} -> {handle_command(text, machines, state)}", flush=True)


async def main(with_m1, calm, quiet):
    machines = {m: Machine(m, cfg, "replay") for m, cfg in REPLAY.items()}
    if with_m1:
        machines.update({m: Machine(m, cfg, "live") for m, cfg in LIVE_STANDIN.items()})
    state = {"random": not calm}

    async with aiomqtt.Client(username=os.getenv("MQTT_USERNAME") or None, password=os.getenv("MQTT_PASSWORD") or None, hostname=os.getenv("MQTT_HOST", "localhost")) as client:
        await client.subscribe(CMD_TOPIC)
        listener = asyncio.create_task(listen(client, machines, state))
        print(f"Simulator jalan: {', '.join(machines)} | kejadian acak: {'nyala' if state['random'] else 'mati'}", flush=True)
        try:
            while True:
                for m in machines.values():
                    await client.publish(f"siagamesin/{m.mid}/telemetry", json.dumps(m.step(state["random"])))
                if not quiet:
                    print(" | ".join(f"{m.mid}:{m.phase}" for m in machines.values()), flush=True)
                await asyncio.sleep(1)
        finally:
            listener.cancel()


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--with-m1", action="store_true", help="simulasikan m1 juga (sebelum rig asli siap)")
    p.add_argument("--calm", action="store_true", help="mulai tanpa kejadian acak")
    p.add_argument("--quiet", action="store_true", help="tidak mencetak fase tiap detik")
    a = p.parse_args()
    try:
        asyncio.run(main(a.with_m1, a.calm, a.quiet))
    except KeyboardInterrupt:
        print("Simulator dihentikan")
