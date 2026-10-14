"use client";

import Link from "next/link";
import { clock, num } from "@/lib/format";
import type { Machine, Reading } from "@/lib/types";
import { condition, StatusBadge } from "./MachineStatus";
import { TrendChart } from "./TrendChart";

export function MachineCard({ machine: m, series }: { machine: Machine; series: Reading[] }) {
  const c = condition(m);
  const frame =
    c.kind === "stopped" ? "border-alarm" : c.kind === "anomaly" ? "border-warn" : "border-rule hover:border-ink-3";
  const trendColor = c.kind === "anomaly" ? "#b8770a" : c.kind === "stopped" ? "#c0392b" : "#8a939d";
  const vibLimit = m.baseline?.vib_rms?.limit_high ?? undefined;
  const vib = m.last?.vib_rms ?? null;
  const vibHot = vib != null && vibLimit != null && vib > vibLimit && c.kind !== "stopped";

  return (
    <Link
      href={`/machines/${m.id}/`}
      className={`block rounded-xl border bg-panel p-4 transition-colors duration-500 ${frame}`}
    >
      <div className="flex items-start justify-between gap-3">
        <div>
          <h3 className="text-[15px] font-semibold leading-tight">
            {m.id.toUpperCase()} <span className="font-normal text-ink-2">{m.name}</span>
          </h3>
          <p className="mt-0.5 text-xs text-ink-3">{m.source === "live" ? "Live rig" : "Simulated"}</p>
        </div>
        <StatusBadge machine={m} />
      </div>

      <dl className={`mt-4 grid grid-cols-3 gap-2 ${m.online ? "" : "text-ink-3"}`}>
        <Value label="Current" value={num(m.last?.current_a, 2)} unit="A" />
        <Value label="Vibration" value={num(vib, 2)} unit="g" hot={vibHot} />
        <Value label="Temp" value={num(m.last?.temp_c, 1)} unit="°C" />
      </dl>

      <div className="mt-3">
        <p className="text-xs text-ink-3">
          {!m.online && m.last ? `No data since ${clock(m.last.ts)} WIB` : "Vibration, last 2 min"}
        </p>
        {series.length > 1 ? (
          <TrendChart values={series.map((h) => h.vib_rms)} color={trendColor} height={44} limit={vibLimit} min={0} />
        ) : (
          <p className="flex h-11 items-center text-xs text-ink-3">{m.online ? "No recent readings" : "Sensor not sending"}</p>
        )}
      </div>

      {m.awaiting_reason && (
        <p className="mt-3 rounded-md bg-alarm-tint px-3 py-2 text-sm text-alarm">
          Bot asked the operator why it stopped. Waiting for a reply.
        </p>
      )}
    </Link>
  );
}

function Value({ label, value, unit, hot }: { label: string; value: string; unit: string; hot?: boolean }) {
  return (
    <div>
      <dt className="text-xs text-ink-2">{label}</dt>
      <dd className={`text-xl font-medium tabular-nums transition-colors ${hot ? "text-warn" : ""}`}>
        {value}
        <span className="ml-0.5 text-xs font-normal text-ink-3">{unit}</span>
      </dd>
    </div>
  );
}
