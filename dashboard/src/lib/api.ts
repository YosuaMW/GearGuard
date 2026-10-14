// Every call to the backend goes through this file.
// - NEXT_PUBLIC_API_URL empty  → in-browser simulator (src/lib/mock.ts)
// - NEXT_PUBLIC_API_URL set    → SiagaMesin FastAPI on the Pi (role 2)
// When login is added later, attach the token in `get()` only.

import { mockGet } from "./mock";
import type {
  AiUsage,
  Alert,
  AvailabilityReport,
  Machine,
  Pareto,
  Range,
  StopEvent,
  Summary,
  TelemetryResponse,
} from "./types";

export const API_URL = (process.env.NEXT_PUBLIC_API_URL ?? "").replace(/\/$/, "");
export const USING_SIMULATOR = API_URL === "";

type Params = Record<string, string | number | boolean | undefined>;

function withQuery(path: string, params?: Params) {
  const q = new URLSearchParams();
  for (const [k, v] of Object.entries(params ?? {})) if (v !== undefined && v !== "") q.set(k, String(v));
  const s = q.toString();
  return s ? `${path}?${s}` : path;
}

async function get<T>(path: string, params?: Params): Promise<T> {
  const full = withQuery(path, params);
  if (USING_SIMULATOR) return (await mockGet(full)) as T;
  const res = await fetch(`${API_URL}${full}`, { cache: "no-store" });
  if (!res.ok) throw new Error(`${path} returned ${res.status}`);
  return res.json() as Promise<T>;
}

export const api = {
  machines: () => get<Machine[]>("/machines"),
  telemetry: (minutes = 2, machine_id?: string) => get<TelemetryResponse>("/telemetry", { minutes, machine_id }),
  summary: (range: Range = "shift") => get<Summary>("/summary", { range }),
  events: (opts: { machine_id?: string; range?: Range; limit?: number } = {}) =>
    get<StopEvent[]>("/events", { range: "today", ...opts }),
  alerts: (opts: { machine_id?: string; active?: boolean; range?: Range } = {}) => get<Alert[]>("/alerts", opts),
  pareto: (range: Range = "shift") => get<Pareto>("/pareto", { range }),
  availability: (range: Range = "shift") => get<AvailabilityReport>("/availability", { range }),
  aiUsage: () => get<AiUsage>("/ai-usage"),
};
