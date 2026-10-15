// How long before a stop did GearGuard warn? Computed in the browser by pairing an
// alert with the first unplanned stop on the same machine after it was raised.
// (The backend closes an alert when the machine stops, so this is usually exact.)

import type { Alert, StopEvent } from "./types";

const MAX_GAP_S = 30 * 60; // a stop more than 30 min after the alert isn't counted as "warned"

export function leadSeconds(alert: Alert, events: StopEvent[] | null | undefined): number | null {
  if (!events) return null;
  const raised = Date.parse(alert.ts);
  let best: number | null = null;
  for (const e of events) {
    if (e.machine_id !== alert.machine_id || e.category_id === "break") continue;
    const gap = (Date.parse(e.start_ts) - raised) / 1000;
    if (gap < 0 || gap > MAX_GAP_S) continue;
    if (best == null || gap < best) best = gap;
  }
  return best == null ? null : Math.round(best);
}

/** Average lead time over alerts that were followed by a stop. */
export function averageLead(alerts: Alert[] | null, events: StopEvent[] | null) {
  const leads = (alerts ?? []).map((a) => leadSeconds(a, events)).filter((x): x is number => x != null);
  if (!leads.length) return null;
  return { avg: Math.round(leads.reduce((t, x) => t + x, 0) / leads.length), count: leads.length };
}

/** Lead time reads best in seconds: "85 s", then "12 min" past ten minutes. */
export function leadText(seconds: number) {
  return seconds < 600 ? `${seconds} s` : `${Math.round(seconds / 60)} min`;
}
