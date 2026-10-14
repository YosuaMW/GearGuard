// Response shapes of the SiagaMesin backend (role 2).
// Source of truth: docs/role4-frontend.md in github.com/YosuaMW/SiagaMesin.
// Times are ISO 8601 UTC; scores and availability are 0–1. Many values can be null.

export type MachineStatus = "running" | "anomaly" | "stopped";
export type Source = "live" | "replay";
export type Range = "shift" | "today" | "1h" | "8h" | "24h";
export type SensorKey = "current_a" | "vib_rms" | "temp_c";

export interface Reading {
  machine_id?: string;
  ts: string;
  current_a: number | null;
  vib_rms: number | null;
  temp_c: number | null;
}

export interface Limit {
  normal: number | null;
  limit_high: number | null;
  limit_low: number | null;
}

/** GET /machines */
export interface Machine {
  id: string;
  name: string;
  source: Source;
  status: MachineStatus;
  online: boolean;
  anomaly_score: number | null;
  awaiting_reason: boolean;
  stopped_since: string | null;
  last: Reading | null;
  baseline: Partial<Record<SensorKey, Limit>> | null;
}

/** GET /telemetry */
export interface TelemetryResponse {
  bucket_seconds: number;
  series: Record<string, Reading[]>;
}

export interface Window {
  range: Range;
  label: string;
  start: string;
  end: string;
  shift_end: string | null;
}

/** GET /summary */
export interface Summary {
  window: Window;
  availability: number | null;
  downtime_minutes: number | null;
  stops: number;
  active_alerts: number;
  stops_without_reason: number;
  data_mode: "live" | "replay" | "offline";
  ai_mode: "mock" | "amd";
}

export type CategoryId =
  | "material"
  | "mechanical"
  | "electrical"
  | "overheat"
  | "changeover"
  | "break"
  | "other"
  | "review";

/** GET /events — one row per stop, with the operator's reason on the same row */
export interface StopEvent {
  id: number;
  machine_id: string;
  machine_name: string;
  source: Source;
  start_ts: string;
  end_ts: string | null;
  ongoing: boolean;
  duration_s: number;
  category_id: CategoryId | null;
  category: string | null;
  confidence: number | null;
  needs_review: boolean;
  has_reason: boolean;
  awaiting_reason: boolean;
  answer_type: "voice" | "text" | "replay" | null;
  transcript: string | null;
}

export interface AlertFeature {
  label: string;
  unit: string;
  now: number | null;
  normal: number | null;
  z: number | null;
  pct: number | null;
}

export interface ManualSource {
  title: string;
  page?: number | null;
  snippet?: string;
}

/** GET /alerts */
export interface Alert {
  id: number;
  machine_id: string;
  machine_name: string;
  source: Source;
  ts: string;
  resolved_ts: string | null;
  active: boolean;
  score: number | null;
  title: string;
  explanation: string;
  explanation_source: "rules" | "ai";
  sources: ManualSource[];
  features: Partial<Record<SensorKey, AlertFeature>>;
}

/** GET /pareto */
export interface Pareto {
  window: Window;
  total_minutes: number | null;
  unexplained_minutes: number | null;
  categories: {
    category_id: CategoryId;
    category: string;
    minutes: number;
    stops: number;
    pct: number;
    cumulative_pct: number;
  }[];
}

/** GET /availability */
export interface AvailabilityReport {
  window: Window;
  line_availability: number | null;
  machines: {
    machine_id: string;
    machine_name: string;
    availability: number | null;
    run_minutes: number | null;
    downtime_minutes: number | null;
    planned_stop_minutes: number | null;
  }[];
}

/** GET /ai-usage */
export interface AiUsage {
  mode: "mock" | "amd";
  since: string;
  endpoints: {
    endpoint: string;
    description: string;
    model: string | null;
    calls_today: number;
    success_rate: number | null;
    avg_latency_ms: number | null;
    prompt_tokens: number | null;
    completion_tokens: number | null;
    mock: boolean | null;
    last_call: string | null;
  }[];
}
