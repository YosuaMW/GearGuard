// Every call to the backend goes through this file.
// - NEXT_PUBLIC_API_URL empty  → in-browser simulator (src/lib/mock.ts)
// - NEXT_PUBLIC_API_URL set    → GearGuard FastAPI on the Pi (role 2)
// When login is added later, attach the token in `get()` only.

import { mockGet, mockPutLimits } from "./mock";
import type {
  AiUsage,
  Alert,
  AvailabilityReport,
  Machine,
  Pareto,
  Limit,
  LimitsUpdate,
  Range,
  SensorKey,
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
  /**
   * Change a machine's alert limits (role 2 endpoint, see README "Alert limits").
   * Body: { vib_rms: { normal, limit_high }, ... }. Returns the machine's new baseline.
   */
  setLimits: async (machineId: string, body: LimitsUpdate) => {
    if (USING_SIMULATOR) return mockPutLimits(machineId, body);
    const KEY_STORE = "gearguard-admin-key";
    let adminKey = "";
    try {
      adminKey = localStorage.getItem(KEY_STORE) ?? "";
    } catch {}
    if (!adminKey) adminKey = (window.prompt("Admin key to change alert limits") ?? "").trim();
    if (!adminKey) throw new Error("An admin key is needed to save limits.");
    let res: Response;
    try {
      res = await fetch(`${API_URL}/machines/${machineId}/limits`, {
        method: "PUT",
        headers: { "Content-Type": "application/json", "X-Admin-Key": adminKey },
        body: JSON.stringify(body),
      });
    } catch {
      throw new Error("The backend didn't accept the request (unreachable, or PUT not allowed in CORS yet).");
    }
    if (res.status === 404 || res.status === 405)
      throw new Error("The backend doesn't support changing limits yet (PUT /machines/{id}/limits).");
    if (res.status === 401) {
      try {
        localStorage.removeItem(KEY_STORE);
      } catch {}
      throw new Error("Wrong admin key. Try saving again.");
    }
    if (res.status === 403) throw new Error("Changing limits is turned off on the backend.");
    if (!res.ok) throw new Error(`Saving failed (${res.status}).`);
    try {
      localStorage.setItem(KEY_STORE, adminKey);
    } catch {}
    return (await res.json()) as Partial<Record<SensorKey, Limit>>;
  },
  /**
   * Every stop in a range for the timeline. The backend returns at most 500 rows per call,
   * and a busy shift has more, so ask per machine and merge (newest first).
   */
  allEvents: async (range: Range, machineIds: string[]) => {
    const lists = await Promise.all(
      machineIds.map((machine_id) => get<StopEvent[]>("/events", { range, machine_id, limit: 500 })),
    );
    const byId = new Map(lists.flat().map((e) => [e.id, e]));
    return [...byId.values()].sort((a, b) => b.start_ts.localeCompare(a.start_ts));
  },
};
