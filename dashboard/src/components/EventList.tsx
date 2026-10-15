"use client";

import { clock, duration } from "@/lib/format";
import { leadSeconds, leadText } from "@/lib/leadtime";
import { usePlant } from "@/lib/plant";
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
  const plant = usePlant();
  const offline = new Set((plant.machines ?? []).filter((m) => !m.online).map((m) => m.id));
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
              <AlertLine a={row.a} showMachine={showMachine} lead={leadSeconds(row.a, plant.events ?? events)} />
            ) : (
              <StopLine e={row.e} showMachine={showMachine} sensorOffline={row.e.ongoing && offline.has(row.e.machine_id)} />
            )}
          </div>
        </li>
      ))}
    </ol>
  );
}

function AlertLine({ a, showMachine, lead }: { a: Alert; showMachine: boolean; lead: number | null }) {
  return (
    <span className="text-warn">
      {showMachine ? `${a.machine_id.toUpperCase()} ` : ""}anomaly alert raised
      {lead != null && <span className="font-medium text-steel"> · warned {leadText(lead)} before the stop</span>}
    </span>
  );
}

function StopLine({ e, showMachine, sensorOffline }: { e: StopEvent; showMachine: boolean; sensorOffline: boolean }) {
  const who = showMachine ? `${e.machine_id.toUpperCase()} ` : "";
  const review = e.needs_review || e.category_id === "review";
  const quote = e.answer_type === "text" ? "Operator" : e.answer_type === "replay" ? "Note" : null;

  if (sensorOffline && !e.has_reason) {
    return (
      <span>
        {who}stopped <span className="text-ink-3">· sensor offline</span>
      </span>
    );
  }

  return (
    <>
      <span>
        {who}stopped{" "}
        <span className="text-ink-2">{e.ongoing ? `${duration(e.duration_s)} so far` : `for ${duration(e.duration_s)}`}</span>
        {e.has_reason ? (
          <>
            {e.category && e.category_id !== "review" && (
              <>
                {" · "}
                <span className="font-medium">{e.category}</span>
              </>
            )}
            {e.confidence != null && <span className="text-xs text-ink-3"> ({Math.round(e.confidence * 100)}%)</span>}
            {review && (
              <span className="ml-1.5 rounded bg-warn-tint px-1.5 py-0.5 align-[1px] text-[11px] font-medium text-warn">
                Needs review
              </span>
            )}
          </>
        ) : (
          <span className="text-alarm">{e.awaiting_reason ? " · waiting for operator reply" : " · no reason yet"}</span>
        )}
      </span>
      {e.transcript && e.answer_type === "voice" && (
        <span className="mt-0.5 flex items-start gap-1.5 text-ink-2" lang="id">
          <MicIcon />
          <span>
            <span className="sr-only">Voice note: </span>“{e.transcript}”
          </span>
        </span>
      )}
      {e.transcript && quote && (
        <span className="mt-0.5 block text-ink-2" lang="id">
          {quote}: “{e.transcript}”
        </span>
      )}
    </>
  );
}

function MicIcon() {
  return (
    <svg
      width="14"
      height="14"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      className="mt-[3px] shrink-0 text-steel"
      aria-label="Voice note"
      role="img"
    >
      <rect x="9" y="3" width="6" height="11" rx="3" />
      <path d="M5.5 11a6.5 6.5 0 0 0 13 0M12 17.5V21" />
    </svg>
  );
}
