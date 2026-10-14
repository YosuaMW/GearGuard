"use client";

import { score100, since } from "@/lib/format";
import type { Machine } from "@/lib/types";

/** One place that decides how a machine's condition is named and coloured. */
export function condition(m: Machine) {
  if (!m.online) return { kind: "offline" as const, text: "Offline", tone: "text-ink-3" };
  if (m.status === "stopped")
    return { kind: "stopped" as const, text: m.stopped_since ? `Stopped ${since(m.stopped_since)}` : "Stopped", tone: "text-alarm" };
  if (m.status === "anomaly") return { kind: "anomaly" as const, text: `Anomaly ${score100(m.anomaly_score)}`, tone: "text-warn" };
  return { kind: "running" as const, text: "Running", tone: "text-ink-2" };
}

export function StatusBadge({ machine }: { machine: Machine }) {
  const c = condition(machine);
  if (c.kind === "running")
    return (
      <span className="flex items-center gap-1.5 text-sm text-ink-2">
        <span className="h-2 w-2 rounded-full bg-run" aria-hidden="true" />
        Running
      </span>
    );
  const cls =
    c.kind === "stopped"
      ? "bg-alarm text-white"
      : c.kind === "anomaly"
        ? "bg-warn-tint text-warn"
        : "bg-paper text-ink-2";
  return <span className={`whitespace-nowrap rounded-md px-2 py-0.5 text-sm font-medium ${cls}`}>{c.text}</span>;
}
