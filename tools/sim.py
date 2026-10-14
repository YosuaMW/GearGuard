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

REASONS = [
    ("Ganti produk/setup", "ganti mold untuk produk B"),
    ("Tunggu material", "material dari gudang belum datang"),
    ("Istirahat/terjadwal", "istirahat shift"),
    ("Breakdown – Listrik", "MCB trip, direset teknisi"),
    ("Breakdown – Overheat", "motor panas, didinginkan dulu"),
    ("Lainnya", "dicek QC"),
]
WEAR_REASON = ("Breakdown – Mekanik", "bearing aus, diganti teknisi")


class Machine:
    def __init__(self, mid, cfg, source):
        self.mid, self.cfg, self.source = mid, cfg, source
        self.phase, self.left = "run", random.randint(60, 180)
        self.wear, self.reason = 0.0, None

    def step(self):
        self.left -= 1
        if self.phase == "run" and self.left <= 0:
            if random.random() < 0.3:
                self.phase, self.left, self.wear = "wear", 90, 0.0
            else:
                self.phase, self.left = "stop", random.randint(20, 60)
                self.reason = random.choice(REASONS)
        elif self.phase == "wear":
            self.wear = min(1.0, self.wear + 1 / 90)
            if self.left <= 0:
                self.phase, self.left, self.reason = "stop", random.randint(30, 60), WEAR_REASON
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


async def main(with_m1):
    machines = [Machine(m, cfg, "replay") for m, cfg in REPLAY.items()]
    if with_m1:
        machines += [Machine(m, cfg, "live") for m, cfg in LIVE_STANDIN.items()]

    async with aiomqtt.Client(os.getenv("MQTT_HOST", "localhost")) as client:
        print(f"Simulator jalan: {', '.join(m.mid for m in machines)}")
        while True:
            for m in machines:
                msg = m.step()
                await client.publish(f"siagamesin/{m.mid}/telemetry", json.dumps(msg))
            print(" | ".join(f"{m.mid}:{m.phase}" for m in machines))
            await asyncio.sleep(1)


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--with-m1", action="store_true", help="simulasikan m1 juga (sebelum rig asli siap)")
    args = p.parse_args()
    try:
        asyncio.run(main(args.with_m1))
    except KeyboardInterrupt:
        print("Simulator dihentikan")
