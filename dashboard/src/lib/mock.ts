// In-browser stand-in for the backend, used when NEXT_PUBLIC_API_URL is empty
// (local development, or the backup deployment if the Pi is unreachable).
// Every response has exactly the shape of the real API (see types.ts).
//
// Scripted scenario, repeats every CYCLE seconds so a demo always has action:
//   m1 Conveyor motor  runs normally
//   m2 Pump            vibration creeps up → alert → stops → operator voice note → restarts
//   m3 Mixer           starts stopped, waiting for the operator; answered at 40 s
//   m4 Compressor      runs normally

import type {
  AiUsage,
  Alert,
  AvailabilityReport,
  CategoryId,
  Machine,
  MachineStatus,
  Pareto,
  Reading,
  SensorKey,
  StopEvent,
  Summary,
  TelemetryResponse,
  Window,
} from "./types";

const CYCLE = 120;
const SHIFT_MIN = 8 * 60;

interface Spec {
  id: string;
  name: string;
  source: "live" | "replay";
  base: Record<SensorKey, number>;
  spread: Record<SensorKey, number>;
}

const SPECS: Spec[] = [
  { id: "m1", name: "Conveyor motor", source: "live", base: { current_a: 1.8, vib_rms: 0.42, temp_c: 41.5 }, spread: { current_a: 0.07, vib_rms: 0.05, temp_c: 0.9 } },
  { id: "m2", name: "Pump", source: "replay", base: { current_a: 2.3, vib_rms: 0.4, temp_c: 45.3 }, spread: { current_a: 0.07, vib_rms: 0.05, temp_c: 0.9 } },
  { id: "m3", name: "Mixer", source: "replay", base: { current_a: 3.1, vib_rms: 0.28, temp_c: 48 }, spread: { current_a: 0.08, vib_rms: 0.04, temp_c: 0.9 } },
  { id: "m4", name: "Compressor", source: "replay", base: { current_a: 1.6, vib_rms: 0.4, temp_c: 40 }, spread: { current_a: 0.06, vib_rms: 0.05, temp_c: 0.8 } },
];

const LABEL: Record<CategoryId, string> = {
  material: "Waiting for material",
  mechanical: "Breakdown – Mechanical",
  electrical: "Breakdown – Electrical",
  overheat: "Breakdown – Overheat",
  changeover: "Changeover / setup",
  break: "Break / scheduled",
  other: "Other",
  review: "Needs review",
};

const r = (n: number, d = 2) => Math.round(n * 10 ** d) / 10 ** d;
const noise = (s: number) => (Math.random() - 0.5) * 2 * s;
const iso = (ms: number) => new Date(ms).toISOString();

interface Live {
  status: MachineStatus;
  awaiting: boolean;
  score: number;
  phase?: string;
  history: Reading[];
}

const state = {
  start: Date.now(),
  tick: -1, // last simulated second since start
  machines: new Map<string, Live>(SPECS.map((s) => [s.id, { status: "running", awaiting: false, score: 0.1, history: [] }])),
  events: [] as StopEvent[],
  alerts: [] as Alert[],
  nextId: 100,
  aiCalls: { transcribe: 0, classify: 0, explain: 0 },
};

function phaseOf(id: string, t: number): { status: MachineStatus; awaiting: boolean; phase: string; drift: number } {
  if (id === "m2") {
    if (t < 45) return { status: "running", awaiting: false, phase: "run", drift: 0 };
    if (t < 80) return { status: "anomaly", awaiting: false, phase: "drift", drift: (t - 45) / 35 };
    if (t < 95) return { status: "stopped", awaiting: true, phase: "stop", drift: 0 };
    if (t < 100) return { status: "stopped", awaiting: false, phase: "answered", drift: 0 };
    return { status: "running", awaiting: false, phase: "run2", drift: 0 };
  }
  if (id === "m3") {
    if (t < 40) return { status: "stopped", awaiting: true, phase: "stop", drift: 0 };
    if (t < 50) return { status: "stopped", awaiting: false, phase: "answered", drift: 0 };
    return { status: "running", awaiting: false, phase: "run2", drift: 0 };
  }
  return { status: "running", awaiting: false, phase: "run", drift: 0 };
}

function spec(id: string) {
  return SPECS.find((s) => s.id === id)!;
}

function openStop(id: string, atMs: number) {
  const s = spec(id);
  state.events.unshift({
    id: state.nextId++,
    machine_id: id,
    machine_name: s.name,
    source: s.source,
    start_ts: iso(atMs),
    end_ts: null,
    ongoing: true,
    duration_s: 0,
    category_id: null,
    category: null,
    confidence: null,
    needs_review: false,
    has_reason: false,
    awaiting_reason: true,
    answer_type: null,
    transcript: null,
  });
}

function answer(id: string, cat: CategoryId, transcript: string, confidence: number) {
  const e = state.events.find((x) => x.machine_id === id && !x.has_reason);
  if (!e) return;
  Object.assign(e, {
    category_id: cat,
    category: LABEL[cat],
    confidence,
    has_reason: true,
    awaiting_reason: false,
    answer_type: "voice",
    transcript,
  });
  state.aiCalls.transcribe++;
  state.aiCalls.classify++;
}

function closeStop(id: string, atMs: number) {
  const e = state.events.find((x) => x.machine_id === id && x.ongoing);
  if (!e) return;
  e.ongoing = false;
  e.end_ts = iso(atMs);
  e.duration_s = Math.round((atMs - Date.parse(e.start_ts)) / 1000);
}

function raiseAlert(atMs: number) {
  state.alerts.unshift({
    id: state.nextId++,
    machine_id: "m2",
    machine_name: "Pump",
    source: "replay",
    ts: iso(atMs),
    resolved_ts: null,
    active: true,
    score: 0.63,
    title: "Vibration rising above normal",
    explanation:
      "Vibration has climbed steadily over the last minutes while current stays flat, a typical sign of bearing wear. Check bearing noise and temperature, bolt tightness and lubrication before the next shift.",
    explanation_source: "ai",
    sources: [
      { title: "Centrifugal pump manual", page: 42 },
      { title: "Repair log, pump seal (Sep 2026)", page: 1 },
    ],
    features: {
      vib_rms: { label: "Vibration", unit: "g RMS", now: 0.62, normal: 0.4, z: 4.1, pct: 55 },
      temp_c: { label: "Temperature", unit: "°C", now: 50.9, normal: 45.3, z: 3.2, pct: 12.4 },
    },
  });
  state.aiCalls.explain++;
}

function resolveAlerts(id: string, atMs: number) {
  for (const a of state.alerts) {
    if (a.machine_id === id && a.active) {
      a.active = false;
      a.resolved_ts = iso(atMs);
    }
  }
}

/** Handles what happens when a machine enters a phase. */
function onPhase(id: string, phase: string, atMs: number) {
  if (phase === "drift") raiseAlert(atMs);
  if (phase === "stop") {
    if (id === "m2") resolveAlerts("m2", atMs);
    openStop(id, atMs);
  }
  if (phase === "answered") {
    if (id === "m2") answer("m2", "mechanical", "bearing bunyi kasar, harus diganti", 0.9);
    else answer(id, "material", "bahan dari gudang belum datang", 0.93);
  }
  if (phase === "run2") closeStop(id, atMs);
}

function reading(s: Spec, status: MachineStatus, drift: number, atMs: number): Reading {
  if (status === "stopped") {
    return { machine_id: s.id, ts: iso(atMs), current_a: r(Math.random() * 0.08), vib_rms: 0.01, temp_c: r(s.base.temp_c - 3 + noise(0.3), 1) };
  }
  return {
    machine_id: s.id,
    ts: iso(atMs),
    current_a: r(s.base.current_a * (1 + 0.04 * drift) + noise(0.06)),
    vib_rms: r(s.base.vib_rms * (1 + 1.2 * drift) + noise(0.025), 3),
    temp_c: r(s.base.temp_c + 9 * drift + noise(0.25), 1),
  };
}

/** Simulates every second since the last call (capped so a sleeping tab catches up quickly). */
function advance() {
  const now = Date.now();
  const target = Math.floor((now - state.start) / 1000);
  let from = state.tick + 1;
  if (target - from > 180) from = target - 180;
  for (let sec = from; sec <= target; sec++) {
    const t = sec % CYCLE;
    const atMs = state.start + sec * 1000;
    for (const s of SPECS) {
      const live = state.machines.get(s.id)!;
      const p = phaseOf(s.id, t);
      if (live.phase !== p.phase) {
        live.phase = p.phase;
        if (sec > 0 || p.phase !== "run") onPhase(s.id, p.phase, atMs);
      }
      live.status = p.status;
      live.awaiting = p.awaiting;
      live.score = p.status === "stopped" ? 0 : r(p.drift > 0 ? 0.45 + 0.45 * p.drift : 0.08 + Math.random() * 0.1);
      live.history.push(reading(s, p.status, p.drift, atMs));
      if (live.history.length > 3600) live.history.shift();
    }
  }
  state.tick = target;
  // keep open stops' duration fresh
  for (const e of state.events) if (e.ongoing) e.duration_s = Math.round((now - Date.parse(e.start_ts)) / 1000);
  state.events = state.events.slice(0, 200);
  state.alerts = state.alerts.slice(0, 50);
}

// Earlier stops today, so the timeline and Pareto aren't empty on first load.
function seed() {
  const now = Date.now();
  const past: [string, number, number, CategoryId, string, number][] = [
    ["m1", 185, 18, "material", "bahan dari gudang belum datang", 0.93],
    ["m4", 240, 12, "changeover", "ganti ukuran produk, setting ulang", 0.88],
    ["m2", 300, 25, "mechanical", "seal pompa bocor, diganti dulu", 0.91],
    ["m3", 360, 15, "break", "istirahat makan siang", 0.97],
    ["m1", 410, 6, "electrical", "kabel sensor lepas", 0.74],
    ["m4", 430, 14, "material", "nunggu palet kosong", 0.86],
    ["m3", 455, 4, "review", "ini kenapa ya tadi", 0.41],
  ];
  for (const [id, minAgo, dur, cat, text, conf] of past) {
    const s = spec(id);
    const start = now - minAgo * 60_000;
    state.events.push({
      id: state.nextId++,
      machine_id: id,
      machine_name: s.name,
      source: s.source,
      start_ts: iso(start),
      end_ts: iso(start + dur * 60_000),
      ongoing: false,
      duration_s: dur * 60,
      category_id: cat,
      category: LABEL[cat],
      confidence: conf,
      needs_review: conf < 0.6,
      has_reason: true,
      awaiting_reason: false,
      answer_type: "voice",
      transcript: text,
    });
  }
  state.events.sort((a, b) => b.start_ts.localeCompare(a.start_ts));
}
seed();

/** Window for a `range` query, shaped like the backend's. The simulator keeps 8 h of history for every range. */
function shiftWindow(range: string = "shift"): Window {
  const wib = new Date(Date.now() + 7 * 3600_000); // shift clock is WIB
  const h = wib.getUTCHours();
  const [no, startH] = h >= 22 || h < 6 ? [3, 22] : h >= 14 ? [2, 14] : [1, 6];
  const endH = (startH + 8) % 24;
  const pad = (n: number) => String(n).padStart(2, "0");
  const labels: Record<string, string> = {
    shift: `Shift ${no} · ${pad(startH)}:00–${pad(endH)}:00`,
    today: "Today",
    "1h": "Last 1 h",
    "8h": "Last 8 h",
    "24h": "Last 24 h",
  };
  return {
    range: (labels[range] ? range : "shift") as Window["range"],
    label: labels[range] ?? labels.shift,
    start: iso(Date.now() - 8 * 3600_000),
    end: iso(Date.now()),
    shift_end: range === "shift" ? iso(Date.now() + 3600_000) : null,
  };
}

function downtimeBy(id?: string) {
  let planned = 0;
  let unplanned = 0;
  for (const e of state.events) {
    if (id && e.machine_id !== id) continue;
    if (e.category_id === "break") planned += e.duration_s;
    else unplanned += e.duration_s;
  }
  return { planned: planned / 60, unplanned: unplanned / 60 };
}

function availability(range = "shift"): AvailabilityReport {
  let run = 0;
  let down = 0;
  const machines = SPECS.map((s) => {
    const d = downtimeBy(s.id);
    const runMin = SHIFT_MIN - d.unplanned - d.planned;
    run += runMin;
    down += d.unplanned;
    return {
      machine_id: s.id,
      machine_name: s.name,
      availability: r(runMin / (runMin + d.unplanned), 4),
      run_minutes: r(runMin, 1),
      downtime_minutes: r(d.unplanned, 1),
      planned_stop_minutes: r(d.planned, 1),
    };
  });
  return { window: shiftWindow(range), line_availability: r(run / (run + down), 4), machines };
}

function machines(): Machine[] {
  return SPECS.map((s) => {
    const live = state.machines.get(s.id)!;
    const open = state.events.find((e) => e.machine_id === s.id && e.ongoing);
    const baseline = Object.fromEntries(
      (Object.keys(s.base) as SensorKey[]).map((k) => [
        k,
        { normal: s.base[k], limit_high: r(s.base[k] + 3 * s.spread[k], 3), limit_low: r(s.base[k] - 3 * s.spread[k], 3) },
      ]),
    );
    return {
      id: s.id,
      name: s.name,
      source: s.source,
      status: live.status,
      online: true,
      anomaly_score: live.score,
      awaiting_reason: live.awaiting,
      stopped_since: live.status === "stopped" ? (open?.start_ts ?? null) : null,
      last: live.history.at(-1) ?? null,
      baseline,
    };
  });
}

export async function mockGet(path: string): Promise<unknown> {
  await new Promise((res) => setTimeout(res, 30));
  advance();
  const url = new URL(path, "http://mock");
  const q = url.searchParams;
  const route = url.pathname.replace(/\/$/, "");
  const machineId = q.get("machine_id") || undefined;

  switch (route) {
    case "/machines":
      return machines();

    case "/telemetry": {
      const minutes = Number(q.get("minutes") ?? 2);
      const since = Date.now() - minutes * 60_000;
      const series: TelemetryResponse["series"] = {};
      for (const s of SPECS) {
        if (machineId && s.id !== machineId) continue;
        series[s.id] = state.machines
          .get(s.id)!
          .history.filter((h) => Date.parse(h.ts) >= since)
          .slice(-120)
          .map(({ ts, current_a, vib_rms, temp_c }) => ({ ts, current_a, vib_rms, temp_c }));
      }
      return { bucket_seconds: 1, series } satisfies TelemetryResponse;
    }

    case "/summary": {
      const av = availability(q.get("range") ?? "shift");
      return {
        window: av.window,
        availability: av.line_availability,
        downtime_minutes: r(state.events.reduce((t, e) => t + e.duration_s, 0) / 60, 1),
        stops: state.events.length,
        active_alerts: state.alerts.filter((a) => a.active).length,
        stops_without_reason: state.events.filter((e) => !e.has_reason).length,
        data_mode: "replay",
        ai_mode: "mock",
      } satisfies Summary;
    }

    case "/events": {
      const limit = Number(q.get("limit") ?? 50);
      return state.events.filter((e) => !machineId || e.machine_id === machineId).slice(0, limit);
    }

    case "/alerts": {
      const activeOnly = q.get("active") === "true";
      return state.alerts.filter((a) => (!machineId || a.machine_id === machineId) && (!activeOnly || a.active));
    }

    case "/pareto": {
      const sums = new Map<CategoryId, { minutes: number; stops: number }>();
      let unexplained = 0;
      for (const e of state.events) {
        if (machineId && e.machine_id !== machineId) continue;
        if (!e.category_id) {
          unexplained += e.duration_s / 60;
          continue;
        }
        const c = sums.get(e.category_id) ?? { minutes: 0, stops: 0 };
        c.minutes += e.duration_s / 60;
        c.stops += 1;
        sums.set(e.category_id, c);
      }
      const total = [...sums.values()].reduce((t, c) => t + c.minutes, 0);
      let cum = 0;
      const categories = [...sums.entries()]
        .sort((a, b) => b[1].minutes - a[1].minutes)
        .map(([id, c]) => {
          cum += c.minutes;
          return {
            category_id: id,
            category: LABEL[id],
            minutes: r(c.minutes, 1),
            stops: c.stops,
            pct: r((c.minutes / total) * 100, 1),
            cumulative_pct: r((cum / total) * 100, 1),
          };
        });
      return { window: shiftWindow(q.get("range") ?? "shift"), total_minutes: r(total, 1), unexplained_minutes: r(unexplained, 1), categories } satisfies Pareto;
    }

    case "/availability":
      return availability(q.get("range") ?? "shift");

    case "/ai-usage": {
      const row = (ep: "transcribe" | "classify" | "explain", description: string, model: string) => ({
        endpoint: `/${ep}`,
        description,
        model,
        calls_today: state.aiCalls[ep],
        success_rate: state.aiCalls[ep] ? 1 : null,
        avg_latency_ms: state.aiCalls[ep] ? { transcribe: 820, classify: 140, explain: 2300 }[ep] : null,
        prompt_tokens: null,
        completion_tokens: null,
        mock: true,
        last_call: null,
      });
      return {
        mode: "mock",
        since: shiftWindow().start,
        endpoints: [
          row("transcribe", "Voice note to text", "mock"),
          row("classify", "Text to downtime reason", "keyword-rules"),
          row("explain", "Alert explanation with manual sources", "mock"),
        ],
      } satisfies AiUsage;
    }

    default:
      throw new Error(`Simulator has no route for ${route}`);
  }
}
