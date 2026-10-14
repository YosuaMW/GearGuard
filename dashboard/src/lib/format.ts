import type { MachineStatus } from "./types";

// The backend sends UTC; the plant reads WIB.
const TZ = "Asia/Jakarta";

export const pct = (x: number | null | undefined) => (x == null ? "–" : `${(x * 100).toFixed(1)}%`);

export const num = (x: number | null | undefined, digits: number) => (x == null ? "–" : x.toFixed(digits));

export const clock = (iso: string) =>
  new Date(iso).toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit", timeZone: TZ });

export const clockSec = (iso: string) =>
  new Date(iso).toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit", second: "2-digit", timeZone: TZ });

export const nowWib = () =>
  new Date().toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit", second: "2-digit", timeZone: TZ });

/** "45s", "6 min", "1 h 12 min" */
export function duration(seconds: number) {
  const s = Math.max(0, Math.round(seconds));
  if (s < 60) return `${s}s`;
  const m = Math.round(s / 60);
  return m < 60 ? `${m} min` : `${Math.floor(m / 60)} h ${m % 60} min`;
}

export function since(iso: string | null, now = Date.now()) {
  return iso ? duration((now - new Date(iso).getTime()) / 1000) : "";
}

export const statusLabel: Record<MachineStatus, string> = {
  running: "Running",
  anomaly: "Anomaly",
  stopped: "Stopped",
};

/** 0.63 → "63" */
export const score100 = (x: number | null | undefined) => (x == null ? "–" : String(Math.round(x * 100)));
