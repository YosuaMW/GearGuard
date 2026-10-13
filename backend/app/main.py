import os
from contextlib import asynccontextmanager

import asyncpg
from dotenv import load_dotenv, find_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

load_dotenv(find_dotenv())

STATUSES = {"running", "anomaly", "stopped"}


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.pool = await asyncpg.create_pool(
        os.environ["DATABASE_URL"], min_size=1, max_size=5
    )
    yield
    await app.state.pool.close()


app = FastAPI(title="SiagaMesin API", lifespan=lifespan)

origins = [o.strip() for o in os.getenv("CORS_ORIGINS", "").split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_methods=["GET"],
    allow_headers=["*"],
)


@app.get("/health")
async def health():
    v = await app.state.pool.fetchval("SELECT version()")
    return {"status": "ok", "db": v.split(",")[0]}


MACHINES_SQL = """
SELECT m.machine_id, m.name, m.source, m.status, m.anomaly_score,
       t.ts, t.current_a, t.vib_rms, t.temp_c,
       e.start_ts, e.end_ts, e.tg_message_id, e.transcript, e.voice_path
FROM machines m
LEFT JOIN LATERAL (
    SELECT ts, current_a, vib_rms, temp_c FROM telemetry
    WHERE machine_id = m.machine_id ORDER BY ts DESC LIMIT 1
) t ON true
LEFT JOIN LATERAL (
    SELECT start_ts, end_ts, tg_message_id, transcript, voice_path FROM events
    WHERE machine_id = m.machine_id ORDER BY start_ts DESC LIMIT 1
) e ON true
ORDER BY m.machine_id
"""


@app.get("/machines")
async def machines():
    rows = await app.state.pool.fetch(MACHINES_SQL)
    result = []
    for r in rows:
        status = r["status"] if r["status"] in STATUSES else "stopped"
        open_event = r["start_ts"] is not None and r["end_ts"] is None
        awaiting = (
            r["tg_message_id"] is not None
            and r["transcript"] is None
            and r["voice_path"] is None
        )
        result.append({
            "id": r["machine_id"],
            "name": r["name"],
            "source": r["source"] or "live",
            "status": status,
            "anomaly_score": r["anomaly_score"],
            "awaiting_reason": awaiting,
            "stopped_since": r["start_ts"] if status == "stopped" and open_event else None,
            "last": {
                "machine_id": r["machine_id"],
                "ts": r["ts"],
                "current_a": r["current_a"],
                "vib_rms": r["vib_rms"],
                "temp_c": r["temp_c"],
            } if r["ts"] else None,
        })
    return result
