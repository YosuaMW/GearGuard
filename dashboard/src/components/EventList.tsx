"use client";

import { clock, duration } from "@/lib/format";
import type { Alert, StopEvent } from "@/lib/types";

type Row = { ts: string; key: string } & ({ kind: "stop"; e: StopEvent } | { kind: "alert"; a: Alert });

/** Today's stops (with the operator's reason) and anomaly alerts, newest first. */
export function EventList({
  events,
  alerts,
  limit = 10,
  showMachine = true,
}: {
  events: StopEvent[] | null;
  alerts?: Alert[] | null;
  limit?: number;
  showMachine?: boolean;
}) {
  const rows: Row[] = [
    ...(events ?? []).map((e) => ({ kind: "stop" as const, ts: e.start_ts, key: `e${e.id}`, e })),
    ...(alerts ?? []).map((a) => ({ kind: "alert" as const, ts: a.ts, key: `a${a.id}`, a })),
  ]
    .sort((x, y) => Date.parse(y.ts) - Date.parse(x.ts))
    .slice(0, limit);

  return (
    <ol className="divide-y divide-rule">
      {rows.length === 0 && <li className="py-3 text-sm text-ink-2">Stops and operator answers will be listed here.</li>}
      {rows.map((row) => (
        <li key={row.key} className="grid grid-cols-[3.25rem_1fr] gap-3 py-2.5 text-sm">
          <time className="tabular-nums text-ink-2">{clock(row.ts)}</time>
          <div>
            {row.kind === "alert" ? (
              <span className="text-warn">
                {showMachine ? `${row.a.machine_id.toUpperCase()} ` : ""}anomaly alert raised
              </span>
            ) : (
              <StopLine e={row.e} showMachine={showMachine} />
            )}
          </div>
        </li>
      ))}
    </ol>
  );
}

function StopLine({ e, showMachine }: { e: StopEvent; showMachine: boolean }) {
  const who = showMachine ? `${e.machine_id.toUpperCase()} ` : "";
  const unsure = e.needs_review || e.category_id === "review";
  const quote =
    e.answer_type === "voice" ? "Voice note" : e.answer_type === "text" ? "Operator" : e.answer_type === "replay" ? "Note" : null;

  return (
    <>
      <span>
        {who}stopped{" "}
        <span className="text-ink-2">{e.ongoing ? `${duration(e.duration_s)} so far` : `for ${duration(e.duration_s)}`}</span>
        {e.has_reason ? (
          <>
            {" · "}
            <span className={`font-medium ${unsure ? "text-warn" : ""}`}>{unsure ? "Needs review" : e.category}</span>
            {e.confidence != null && <span className="text-xs text-ink-3"> ({Math.round(e.confidence * 100)}%)</span>}
          </>
        ) : (
          <span className="text-alarm">{e.awaiting_reason ? " · waiting for operator reply" : " · no reason yet"}</span>
        )}
      </span>
      {e.transcript && quote && (
        <span className="mt-0.5 block text-ink-2" lang="id">
          {quote}: “{e.transcript}”
        </span>
      )}
    </>
  );
}
