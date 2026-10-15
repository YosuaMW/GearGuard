// Maintenance figures computed in the browser from /events and /availability.
//
// Breakdown = a stop whose reason is mechanical, electrical or overheat.
// MTTR = average breakdown duration.  MTBF = run time ÷ number of breakdowns.

import type { AvailabilityReport, CategoryId, StopEvent } from "./types";

export const BREAKDOWNS: CategoryId[] = ["mechanical", "electrical", "overheat"];

export interface MachineMaintenance {
  machine_id: string;
  machine_name: string;
  availability: number | null;
  downtimeMin: number;
  runMin: number;
  breakdowns: number;
  mttrMin: number | null;
  mtbfMin: number | null;
}

export function maintenanceByMachine(events: StopEvent[], avail: AvailabilityReport): MachineMaintenance[] {
  return avail.machines.map((m) => {
    const bd = events.filter((e) => e.machine_id === m.machine_id && e.category_id && BREAKDOWNS.includes(e.category_id));
    const repairMin = bd.reduce((t, e) => t + e.duration_s / 60, 0);
    const run = m.run_minutes ?? 0;
    return {
      machine_id: m.machine_id,
      machine_name: m.machine_name,
      availability: m.availability,
      downtimeMin: m.downtime_minutes ?? 0,
      runMin: run,
      breakdowns: bd.length,
      mttrMin: bd.length ? repairMin / bd.length : null,
      mtbfMin: bd.length ? run / bd.length : null,
    };
  });
}

export function unplannedMinutes(avail: AvailabilityReport | null) {
  return avail ? avail.machines.reduce((t, m) => t + (m.downtime_minutes ?? 0), 0) : null;
}
