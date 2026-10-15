import json
import os
import time
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from dotenv import load_dotenv, find_dotenv
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

load_dotenv(find_dotenv())

from app import db, labels  # noqa: E402

STATUSES = {"running", "anomaly", "stopped"}
STOP_A = float(os.getenv("STOP_CURRENT_A", "0.3"))
SAMPLE_S = float(os.getenv("SAMPLE_SECONDS", "1"))
Z_ALERT = float(os.getenv("ANOMALY_Z_ALERT", "3"))
FEATURES = {
    "current_a": ("Current", "A"),
    "vib_rms": ("Vibration", "g RMS"),
    "temp_c": ("Temperature", "°C"),
}
RANGE = Query("shift", pattern="^(shift|today|1h|8h|24h)$")


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.pool = await db.create_pool(max_size=5)
    await app.state.pool.execute("CREATE INDEX IF NOT EXISTS telemetry_ts ON telemetry (ts)")
    yield
    await app.state.pool.close()


app = FastAPI(title="GearGuard API", version="0.2.0", lifespan=lifespan)

origins = [o.strip() for o in os.getenv("CORS_ORIGINS", "").split(",") if o.strip()]
app.add_middleware(CORSMiddleware, allow_origins=origins, allow_methods=["GET"], allow_headers=["*"])

_cache = {}


async def cached(key, ttl, fn):
    now = time.monotonic()
    hit = _cache.get(key)
    if hit and now - hit[0] < ttl:
        return hit[1]
    val = await fn()
    _cache[key] = (now, val)
    return val


def pool():
    return app.state.pool


def jload(v):
    if v is None:
        return None
    return json.loads(v) if isinstance(v, str) else v


def rnd(v, n=3):
    return None if v is None else round(float(v), n)


# ---------------------------------------------------------------- health / machines

@app.get("/health")
async def health():
    v = await pool().fetchval("SELECT version()")
    return {"status": "ok", "db": v.split(",")[0]}


MACHINES_SQL = """
SELECT m.machine_id, m.name, m.source, m.status, m.anomaly_score, b.stats,
       t.ts, t.current_a, t.vib_rms, t.temp_c,
       e.start_ts, e.end_ts, e.tg_message_id, e.category
FROM machines m
LEFT JOIN baselines b ON b.machine_id = m.machine_id
LEFT JOIN LATERAL (
    SELECT ts, current_a, vib_rms, temp_c FROM telemetry
    WHERE machine_id = m.machine_id ORDER BY ts DESC LIMIT 1
) t ON true
LEFT JOIN LATERAL (
    SELECT start_ts, end_ts, tg_message_id, category FROM events
    WHERE machine_id = m.machine_id ORDER BY start_ts DESC LIMIT 1
) e ON true
ORDER BY m.machine_id
"""


def baseline_out(stats):
    stats = jload(stats)
    if not stats:
        return None
    out = {}
    for f, s in stats.items():
        med, scale = s["median"], s["scale"]
        out[f] = {"normal": rnd(med), "limit_high": rnd(med + Z_ALERT * scale), "limit_low": rnd(med - Z_ALERT * scale)}
    return out


@app.get("/machines")
async def machines():
    rows = await pool().fetch(MACHINES_SQL)
    now = datetime.now(timezone.utc)
    result = []
    for r in rows:
        status = r["status"] if r["status"] in STATUSES else "stopped"
        open_event = r["start_ts"] is not None and r["end_ts"] is None
        online = r["ts"] is not None and (now - r["ts"]).total_seconds() <= 30
        if not online:
            status = "stopped"   # tidak ada data > 30 detik = dianggap berhenti
        result.append({
            "id": r["machine_id"],
            "name": r["name"],
            "source": r["source"] or "live",
            "status": status,
            "online": online,
            "anomaly_score": rnd(r["anomaly_score"]),
            "awaiting_reason": r["tg_message_id"] is not None and r["category"] is None,
            "stopped_since": (r["start_ts"] if open_event else r["ts"]) if status == "stopped" else None,
            "last": {
                "machine_id": r["machine_id"],
                "ts": r["ts"],
                "current_a": rnd(r["current_a"], 2),
                "vib_rms": rnd(r["vib_rms"], 3),
                "temp_c": rnd(r["temp_c"], 1),
            } if r["ts"] else None,
            "baseline": baseline_out(r["stats"]),
        })
    return result


@app.get("/telemetry")
async def telemetry(machine_id: str | None = None, minutes: float = Query(2, gt=0, le=60)):
    """Data sensor untuk grafik, dirata-rata per bucket supaya maksimal ±120 titik per mesin."""
    bucket = max(SAMPLE_S, minutes * 60 / 120)
    rows = await pool().fetch(
        """SELECT machine_id,
                  to_timestamp(floor(extract(epoch FROM ts) / $3) * $3) AS t,
                  avg(current_a) AS current_a, avg(vib_rms) AS vib_rms, avg(temp_c) AS temp_c
           FROM telemetry
           WHERE ts > now() - make_interval(secs => $1) AND ($2::text IS NULL OR machine_id = $2)
           GROUP BY machine_id, t ORDER BY machine_id, t""",
        minutes * 60, machine_id, bucket,
    )
    out = {}
    for r in rows:
        out.setdefault(r["machine_id"], []).append({
            "ts": r["t"], "current_a": rnd(r["current_a"], 2),
            "vib_rms": rnd(r["vib_rms"], 3), "temp_c": rnd(r["temp_c"], 1),
        })
    return {"bucket_seconds": bucket, "series": out}


# ---------------------------------------------------------------- events

def event_out(r, now):
    end = r["end_ts"]
    ongoing = end is None
    effective_end = end or min(now, r["last_seen"] or now)
    duration = max((effective_end - r["start_ts"]).total_seconds(), 0)
    answer = "voice" if r["voice_path"] else ("text" if r["transcript"] else None)
    if r["source"] == "replay" and r["category"]:
        answer = "replay"
    return {
        "id": r["id"],
        "machine_id": r["machine_id"],
        "machine_name": r["name"],
        "source": r["source"],
        "start_ts": r["start_ts"],
        "end_ts": end,
        "ongoing": ongoing,
        "duration_s": round(duration),
        "category_id": labels.category_id(r["category"]),
        "category": labels.label(r["category"]),
        "confidence": rnd(r["confidence"], 2),
        "needs_review": bool(r["needs_review"]),
        "has_reason": r["category"] is not None,
        "awaiting_reason": r["tg_message_id"] is not None and r["category"] is None,
        "answer_type": answer,
        "transcript": r["transcript"],
    }


@app.get("/events")
async def events(machine_id: str | None = None, range: str = Query("today", pattern="^(shift|today|1h|8h|24h)$"),
                 limit: int = Query(50, ge=1, le=500)):
    b = labels.range_bounds(range)
    rows = await pool().fetch(
        """SELECT e.*, m.name, m.source, m.last_seen
           FROM events e JOIN machines m USING (machine_id)
           WHERE e.start_ts < $2 AND COALESCE(e.end_ts, now()) > $1
             AND ($3::text IS NULL OR e.machine_id = $3)
           ORDER BY e.start_ts DESC LIMIT $4""",
        b["start"], b["end"], machine_id, limit,
    )
    now = datetime.now(timezone.utc)
    return [event_out(r, now) for r in rows]


# ---------------------------------------------------------------- alerts

RULES = {
    ("vib_rms", True): ("Vibration rising above normal",
                        "Vibration is above its normal level, a typical sign of bearing wear, imbalance or loose mounting bolts. "
                        "Check bearing noise and temperature, bolt tightness and lubrication."),
    ("temp_c", True): ("Temperature rising above normal",
                       "Motor temperature is rising. The cooling fan or vents may be blocked, or the machine is overloaded. "
                       "Check the cooling fan, motor fins and machine load."),
    ("current_a", True): ("Current above normal",
                          "The motor is drawing more current than normal, usually overload or mechanical friction. "
                          "Check the load, shaft alignment and lubrication."),
    ("current_a", False): ("Current dropped below normal",
                           "Current dropped below normal. The load may be lost, the belt slipping or broken, or the coupling loose. "
                           "Check the belt, coupling and load connection."),
}


def features_out(raw):
    """Mendukung format lama {f: z} dan format baru {f: {now, normal, z}}."""
    raw = jload(raw) or {}
    out = {}
    for f, v in raw.items():
        name, unit = FEATURES.get(f, (f, ""))
        if isinstance(v, dict):
            now, normal = v.get("now"), v.get("normal")
            pct = (now - normal) / normal * 100 if now is not None and normal else None
            out[f] = {"label": name, "unit": unit, "now": rnd(now), "normal": rnd(normal),
                      "z": rnd(v.get("z"), 2), "pct": rnd(pct, 1)}
        else:
            out[f] = {"label": name, "unit": unit, "now": None, "normal": None, "z": rnd(v, 2), "pct": None}
    return out


def alert_text(feats):
    if not feats:
        return "Sensor pattern deviates from normal", "Perform a visual inspection of the machine."
    top = max(feats, key=lambda f: feats[f]["z"] or 0)
    t = feats[top]
    up = True if t["pct"] is None else t["pct"] >= 0
    return RULES.get((top, up), ("Sensor pattern deviates from normal", "Perform a visual inspection of the machine."))


@app.get("/alerts")
async def alerts(machine_id: str | None = None, active: bool = False,
                 range: str = Query("today", pattern="^(shift|today|1h|8h|24h)$"),
                 limit: int = Query(50, ge=1, le=500)):
    b = labels.range_bounds(range)
    rows = await pool().fetch(
        """SELECT a.*, m.name, m.source
           FROM alerts a JOIN machines m USING (machine_id)
           WHERE (a.resolved_ts IS NULL OR (NOT $3 AND a.ts >= $1))
             AND ($2::text IS NULL OR a.machine_id = $2)
           ORDER BY a.ts DESC LIMIT $4""",
        b["start"], machine_id, active, limit,
    )
    out = []
    for r in rows:
        feats = features_out(r["features"])
        title, rule_text = alert_text(feats)
        out.append({
            "id": r["id"],
            "machine_id": r["machine_id"],
            "machine_name": r["name"],
            "source": r["source"],
            "ts": r["ts"],
            "resolved_ts": r["resolved_ts"],
            "active": r["resolved_ts"] is None,
            "score": rnd(r["score"]),
            "title": title,
            "explanation": r["explanation"] or rule_text,
            "explanation_source": "ai" if r["explanation"] else "rules",
            "sources": jload(r["sources"]) or [],
            "features": feats,
        })
    return out


# ---------------------------------------------------------------- reports

STOPS_SQL = """
SELECT e.machine_id, e.category,
       GREATEST(EXTRACT(EPOCH FROM LEAST(COALESCE(e.end_ts, LEAST(now(), m.last_seen)), $2)
                                 - GREATEST(e.start_ts, $1)), 0) AS secs
FROM events e JOIN machines m USING (machine_id)
WHERE e.start_ts < $2 AND COALESCE(e.end_ts, now()) > $1
"""


async def _availability(b):
    p = pool()
    run = await p.fetch(
        "SELECT machine_id, count(*) AS n FROM telemetry WHERE ts >= $1 AND ts < $2 AND current_a >= $3 GROUP BY machine_id",
        b["start"], b["end"], STOP_A,
    )
    stops = await p.fetch(STOPS_SQL, b["start"], b["end"])
    names = await p.fetch("SELECT machine_id, name FROM machines ORDER BY machine_id")
    run_s = {r["machine_id"]: r["n"] * SAMPLE_S for r in run}
    planned, unplanned = {}, {}
    for s in stops:
        bucket = planned if s["category"] in labels.PLANNED else unplanned
        bucket[s["machine_id"]] = bucket.get(s["machine_id"], 0) + float(s["secs"])
    machines_out, tot_run, tot_down = [], 0.0, 0.0
    for n in names:
        mid = n["machine_id"]
        r, d = run_s.get(mid, 0.0), unplanned.get(mid, 0.0)
        tot_run, tot_down = tot_run + r, tot_down + d
        machines_out.append({
            "machine_id": mid, "machine_name": n["name"],
            "availability": rnd(r / (r + d), 4) if r + d > 0 else None,
            "run_minutes": rnd(r / 60, 1), "downtime_minutes": rnd(d / 60, 1),
            "planned_stop_minutes": rnd(planned.get(mid, 0.0) / 60, 1),
        })
    line = rnd(tot_run / (tot_run + tot_down), 4) if tot_run + tot_down > 0 else None
    return {"line_availability": line, "machines": machines_out}


def window(b):
    return {"range": b["range"], "label": b["label"], "start": b["start"], "end": b["end"], "shift_end": b["shift_end"]}


@app.get("/availability")
async def availability(range: str = RANGE):
    async def run():
        b = labels.range_bounds(range)
        return {"window": window(b), **await _availability(b)}
    return await cached(("availability", range), 5, run)


@app.get("/pareto")
async def pareto(range: str = RANGE, machine_id: str | None = None):
    async def run():
        b = labels.range_bounds(range)
        rows = await pool().fetch(STOPS_SQL, b["start"], b["end"])
        sums, counts, unexplained = {}, {}, 0.0
        for r in rows:
            if machine_id and r["machine_id"] != machine_id:
                continue
            if r["category"] is None:
                unexplained += float(r["secs"])
                continue
            sums[r["category"]] = sums.get(r["category"], 0.0) + float(r["secs"])
            counts[r["category"]] = counts.get(r["category"], 0) + 1
        total = sum(sums.values())
        cats, cum = [], 0.0
        for c, s in sorted(sums.items(), key=lambda kv: kv[1], reverse=True):
            cum += s
            cats.append({
                "category_id": labels.category_id(c), "category": labels.label(c),
                "minutes": rnd(s / 60, 1), "stops": counts[c],
                "pct": rnd(s / total * 100, 1) if total else 0, "cumulative_pct": rnd(cum / total * 100, 1) if total else 0,
            })
        return {"window": window(b), "total_minutes": rnd(total / 60, 1),
                "unexplained_minutes": rnd(unexplained / 60, 1), "categories": cats}
    return await cached(("pareto", range, machine_id), 5, run)


@app.get("/summary")
async def summary(range: str = RANGE):
    """Angka ringkas untuk baris KPI di halaman Overview."""
    async def run():
        b = labels.range_bounds(range)
        p = pool()
        av = await _availability(b)
        stops = await p.fetch(STOPS_SQL, b["start"], b["end"])
        active = await p.fetchval("SELECT count(*) FROM alerts WHERE resolved_ts IS NULL")
        no_reason = await p.fetchval(
            "SELECT count(*) FROM events WHERE category IS NULL AND start_ts < $2 AND COALESCE(end_ts, now()) > $1",
            b["start"], b["end"])
        online = await p.fetch("SELECT DISTINCT m.source FROM machines m WHERE m.last_seen > now() - interval '30 seconds'")
        sources = {r["source"] for r in online}
        return {
            "window": window(b),
            "availability": av["line_availability"],
            "downtime_minutes": rnd(sum(float(s["secs"]) for s in stops) / 60, 1),
            "stops": len(stops),
            "active_alerts": active,
            "stops_without_reason": no_reason,
            "data_mode": "replay" if sources == {"replay"} else ("offline" if not sources else "live"),
            "ai_mode": "amd" if os.getenv("AI_BASE_URL") else "mock",
        }
    return await cached(("summary", range), 3, run)


# ---------------------------------------------------------------- AI usage

AI_ENDPOINTS = [
    ("transcribe", "Voice note to text"),
    ("classify", "Text to downtime reason"),
    ("explain", "Alert explanation with manual sources"),
]


@app.get("/ai-usage")
async def ai_usage():
    start = labels.range_bounds("today")["start"]
    rows = await pool().fetch(
        """SELECT endpoint, count(*) AS calls, count(*) FILTER (WHERE ok) AS ok_calls,
                  avg(latency_ms) AS avg_latency, sum(prompt_tokens) AS pt, sum(completion_tokens) AS ct,
                  bool_and(mock) AS all_mock,
                  (array_agg(model ORDER BY id DESC) FILTER (WHERE model IS NOT NULL))[1] AS model,
                  max(ts) AS last_call
           FROM ai_calls WHERE ts >= $1 GROUP BY endpoint""",
        start,
    )
    by = {r["endpoint"]: r for r in rows}
    out = []
    for ep, desc in AI_ENDPOINTS:
        r = by.get(ep)
        out.append({
            "endpoint": f"/{ep}", "description": desc,
            "model": r["model"] if r else None,
            "calls_today": r["calls"] if r else 0,
            "success_rate": rnd(r["ok_calls"] / r["calls"], 3) if r and r["calls"] else None,
            "avg_latency_ms": round(r["avg_latency"]) if r and r["avg_latency"] is not None else None,
            "prompt_tokens": r["pt"] if r else None,
            "completion_tokens": r["ct"] if r else None,
            "mock": bool(r["all_mock"]) if r else None,
            "last_call": r["last_call"] if r else None,
        })
    return {"mode": "amd" if os.getenv("AI_BASE_URL") else "mock", "since": start, "endpoints": out}


@app.get("/machines/{machine_id}")
async def machine_detail(machine_id: str):
    for m in await machines():
        if m["id"] == machine_id:
            return m
    raise HTTPException(404, "machine not found")
