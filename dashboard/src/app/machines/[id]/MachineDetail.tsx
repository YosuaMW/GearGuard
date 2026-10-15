"use client";

import Link from "next/link";
import { AlertExplanation } from "@/components/AlertPanel";
import { EventList } from "@/components/EventList";
import { condition } from "@/components/MachineStatus";
import { TrendChart } from "@/components/TrendChart";
import { clockSec, num, score100 } from "@/lib/format";
import { usePlant } from "@/lib/plant";
import type { Machine, Reading, SensorKey } from "@/lib/types";

const SENSORS: { key: SensorKey; title: string; unit: string; digits: number; zero: boolean }[] = [
  { key: "vib_rms", title: "Vibration", unit: "g RMS", digits: 2, zero: true },
  { key: "current_a", title: "Current", unit: "A", digits: 2, zero: true },
  { key: "temp_c", title: "Temperature", unit: "°C", digits: 1, zero: false },
];

export function MachineDetail({ id }: { id: string }) {
  const { machines, telemetry, events, alerts } = usePlant();
  if (!machines) return <p className="py-20 text-center text-ink-2">Connecting to the line…</p>;
  const m = machines.find((x) => x.id === id);
  if (!m) return <p className="py-20 text-center text-ink-2">No machine with id {id}.</p>;

  const series = telemetry?.series[id] ?? [];
  const myAlerts = alerts?.filter((a) => a.machine_id === id) ?? [];
  const active = myAlerts.find((a) => a.active);
  const c = condition(m);

  return (
    <div className="space-y-5">
      <nav aria-label="Machines" className="flex flex-wrap gap-2">
        {machines.map((x) => (
          <Link
            key={x.id}
            href={`/machines/${x.id}/`}
            className={`rounded-md border px-3 py-1.5 text-sm ${
              x.id === id ? "border-steel bg-steel/10 font-medium text-steel" : "border-rule bg-panel text-ink-2 hover:text-ink"
            }`}
          >
            {x.id.toUpperCase()} {x.name}
          </Link>
        ))}
      </nav>

      <header>
        <h1 className="text-2xl font-semibold tracking-tight">
          {m.id.toUpperCase()} {m.name}
        </h1>
        <p className={`mt-1 text-sm ${c.tone}`}>
          {c.text}
          {c.kind !== "stopped" && c.kind !== "offline" && ` · anomaly score ${score100(m.anomaly_score)} / 100`}
          <span className="text-ink-3"> · {m.source === "live" ? "Live rig" : "Simulated"}</span>
        </p>
      </header>

      {m.awaiting_reason && (
        <p className="rounded-xl border border-alarm bg-alarm-tint px-4 py-3 text-sm text-alarm">
          The bot asked the operator on Telegram why this machine stopped. Waiting for a reply.
        </p>
      )}

      {active && (
        <section className="rounded-xl border border-warn bg-warn-tint/60 p-4">
          <h2 className="font-semibold text-warn">{active.title}</h2>
          <div className="max-w-[80ch]">
            <AlertExplanation alert={active} />
          </div>
        </section>
      )}

      {!m.baseline && (
        <p className="text-sm text-ink-2">Alert limits appear once the backend has learned this machine&apos;s normal pattern.</p>
      )}

      <div className="grid gap-4 lg:grid-cols-3">
        {SENSORS.map((s) => (
          <SensorPanel key={s.key} machine={m} series={series} sensor={s} />
        ))}
      </div>

      <section className="rounded-xl border border-rule bg-panel p-4">
        <h2 className="text-[15px] font-semibold">Stops and operator answers today</h2>
        <EventList
          events={events?.filter((e) => e.machine_id === id) ?? null}
          alerts={myAlerts}
          limit={15}
          showMachine={false}
        />
      </section>
    </div>
  );
}

function SensorPanel({
  machine: m,
  series,
  sensor: s,
}: {
  machine: Machine;
  series: Reading[];
  sensor: (typeof SENSORS)[number];
}) {
  const limit = m.baseline?.[s.key]?.limit_high ?? undefined;
  const normal = m.baseline?.[s.key]?.normal;
  const value = m.last?.[s.key] ?? null;
  const over = value != null && limit != null && value > limit && m.status !== "stopped";
  const color = over || (m.status === "anomaly" && s.key === "vib_rms") ? "#b8770a" : "#2f5d8c";

  return (
    <section className="rounded-xl border border-rule bg-panel p-4">
      <div className="flex items-baseline justify-between">
        <h2 className="text-[15px] font-semibold">{s.title}</h2>
        <p className={`text-xl font-medium tabular-nums ${over ? "text-warn" : ""}`}>
          {num(value, s.digits)} <span className="text-xs font-normal text-ink-3">{s.unit}</span>
        </p>
      </div>
      {normal != null && (
        <p className="text-xs text-ink-3">
          Normal {normal}
          {limit != null && ` · alert above ${limit}`}
        </p>
      )}
      <div className="mt-2">
        {series.length > 1 ? (
          <TrendChart
            detailed
            values={series.map((p) => p[s.key])}
            times={series.map((p) => clockSec(p.ts))}
            height={200}
            limit={limit}
            unit={s.unit}
            color={color}
            min={s.zero ? 0 : undefined}
          />
        ) : (
          <p className="flex h-[200px] items-center justify-center text-sm text-ink-3">No readings in the last 2 minutes</p>
        )}
      </div>
    </section>
  );
}
