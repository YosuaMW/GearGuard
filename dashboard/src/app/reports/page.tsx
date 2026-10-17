"use client";

import ReactEChartsCore from "echarts-for-react/lib/core";
import * as echarts from "echarts/core";
import { BarChart, LineChart } from "echarts/charts";
import { GridComponent, TooltipComponent } from "echarts/components";
import { CanvasRenderer } from "echarts/renderers";
import { useCallback, useState } from "react";
import { StateTimeline } from "@/components/StateTimeline";
import { api } from "@/lib/api";
import { duration, pct } from "@/lib/format";
import { averageLead, leadText } from "@/lib/leadtime";
import { maintenanceByMachine, unplannedMinutes } from "@/lib/maintenance";
import { usePlant } from "@/lib/plant";
import { rupiah, setPrefs, usePrefs } from "@/lib/prefs";
import type { Range } from "@/lib/types";
import { usePolling } from "@/lib/usePolling";
import { useWide } from "@/lib/useWide";

echarts.use([BarChart, LineChart, GridComponent, TooltipComponent, CanvasRenderer]);

const FONT = { fontFamily: "IBM Plex Sans", color: "#5b6672", fontSize: 12 };

const RANGES: { value: Range; label: string }[] = [
  { value: "shift", label: "This shift" },
  { value: "today", label: "Today" },
  { value: "24h", label: "Last 24 h" },
];

export default function ReportsPage() {
  const [range, setRange] = useState<Range>("shift");
  // New fetcher when the range changes, so the polling hook picks it up on its next tick.
  const fetchPareto = useCallback(() => api.pareto(range), [range]);
  const fetchAvail = useCallback(() => api.availability(range), [range]);
  const { machines: live } = usePlant();
  const ids = (live?.map((m) => m.id) ?? ["m1", "m2", "m3", "m4"]).join(",");
  const fetchEvents = useCallback(() => api.allEvents(range, ids.split(",")), [range, ids]);
  const fetchAlerts = useCallback(() => api.alerts({ range }), [range]);
  const pareto = usePolling(fetchPareto, 10_000).data;
  const avail = usePolling(fetchAvail, 10_000).data;
  const events = usePolling(fetchEvents, 5_000).data;
  const alerts = usePolling(fetchAlerts, 5_000).data;
  const { costPerMin } = usePrefs();
  const wide = useWide();

  const cats = pareto?.window.range === range ? pareto.categories : [];
  const machines = avail?.window.range === range ? avail.machines : [];

  const paretoOption = {
    animationDuration: 400,
    grid: { left: 48, right: 44, top: 32, bottom: wide ? 72 : 96 },
    tooltip: { trigger: "axis", textStyle: { fontFamily: "IBM Plex Sans" } },
    xAxis: {
      type: "category",
      data: cats.map((p) => p.category),
      axisLabel: wide ? { ...FONT, interval: 0, width: 90, overflow: "break" } : { ...FONT, interval: 0, rotate: 40, width: 90, overflow: "truncate" },
      axisTick: { show: false },
      axisLine: { lineStyle: { color: "#d5dae0" } },
    },
    yAxis: [
      { type: "value", name: "min", nameTextStyle: FONT, axisLabel: FONT, splitLine: { lineStyle: { color: "#eef0f3" } } },
      { type: "value", max: 100, axisLabel: { ...FONT, formatter: "{value}%" }, splitLine: { show: false } },
    ],
    series: [
      {
        name: "Downtime (min)",
        type: "bar",
        data: cats.map((p, i) => ({ value: p.minutes, itemStyle: { color: i === 0 ? "#2f5d8c" : "#9fb3c8" } })),
        barMaxWidth: 48,
        itemStyle: { borderRadius: [3, 3, 0, 0] },
      },
      {
        name: "Cumulative (%)",
        type: "line",
        yAxisIndex: 1,
        data: cats.map((p) => p.cumulative_pct),
        symbolSize: 6,
        lineStyle: { color: "#17202b", width: 1.5 },
        itemStyle: { color: "#17202b" },
      },
    ],
  };

  const availOption = {
    animationDuration: 400,
    grid: { left: 36, right: 56, top: 8, bottom: 8 },
    xAxis: { type: "value", max: 100, show: false },
    yAxis: {
      type: "category",
      inverse: true,
      data: machines.map((p) => p.machine_id.toUpperCase()),
      axisLabel: { ...FONT, color: "#17202b", fontSize: 13 },
      axisTick: { show: false },
      axisLine: { show: false },
    },
    series: [
      {
        type: "bar",
        data: machines.map((p) =>
          p.availability == null
            ? { value: 0, label: { formatter: "No data", color: "#8a939d" } }
            : Math.round(p.availability * 1000) / 10,
        ),
        barWidth: 14,
        showBackground: true,
        backgroundStyle: { color: "#eef0f3", borderRadius: 3 },
        itemStyle: { color: "#2f5d8c", borderRadius: 3 },
        label: { show: true, position: "right", formatter: "{c}%", ...FONT, color: "#17202b" },
      },
    ],
  };

  const top = cats[0];
  const total = pareto?.total_minutes ?? 0;
  const win = avail?.window.range === range ? avail.window : null;
  const lineMachines = live?.map((m) => ({ id: m.id, name: m.name })) ?? machines.map((m) => ({ id: m.machine_id, name: m.machine_name }));
  const maint = avail && win && events ? maintenanceByMachine(events, avail) : [];
  const unplanned = win ? unplannedMinutes(avail) : null;
  const lead = win ? averageLead(alerts, events) : null;

  return (
    <div className="space-y-5">
      <header className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Downtime report</h1>
          <p className="mt-1 text-sm text-ink-2">
            All machines on Line A{pareto ? `, ${pareto.window.label}` : ""}. Reasons come from operator voice notes.
          </p>
        </div>
        <div role="group" aria-label="Time range" className="flex rounded-md border border-rule bg-panel p-0.5">
          {RANGES.map((r) => (
            <button
              key={r.value}
              type="button"
              onClick={() => setRange(r.value)}
              aria-pressed={range === r.value}
              className={`rounded px-3 py-1 text-sm ${range === r.value ? "bg-steel/10 font-medium text-steel" : "text-ink-2 hover:text-ink"}`}
            >
              {r.label}
            </button>
          ))}
        </div>
      </header>

      <section className="rounded-xl border border-rule bg-panel p-4">
        <h2 className="text-[15px] font-semibold">What each machine was doing</h2>
        <p className="mt-1 text-sm text-ink-2">Hover a bar to see the reason and how long it lasted.</p>
        <div className="mt-2">
          {win && events && alerts ? (
            <StateTimeline machines={lineMachines} events={events} alerts={alerts} start={win.start} end={win.end} />
          ) : (
            <p className="py-10 text-center text-sm text-ink-3">Loading timeline…</p>
          )}
        </div>
      </section>

      <div className="grid gap-5 lg:grid-cols-[minmax(0,2fr)_minmax(0,1fr)]">
        <section className="rounded-xl border border-rule bg-panel p-4">
          <h2 className="text-[15px] font-semibold">Where the time went</h2>
          {top && total > 0 ? (
            <p className="mt-1 text-sm text-ink-2">
              {top.category} caused {Math.round(top.pct)}% of downtime ({top.minutes} of {total} min).
              {!!pareto?.unexplained_minutes && ` ${pareto.unexplained_minutes} min still has no reason.`}
            </p>
          ) : (
            <p className="mt-1 text-sm text-ink-2">No stops with a reason in this period yet.</p>
          )}
          <ReactEChartsCore echarts={echarts} option={paretoOption} notMerge style={{ height: 320 }} />
        </section>

        <section className="rounded-xl border border-rule bg-panel p-4">
          <h2 className="text-[15px] font-semibold">Availability by machine</h2>
          <p className="mt-1 text-sm text-ink-2">
            Line {pct(avail?.line_availability)}. Scheduled breaks don&apos;t count as downtime.
          </p>
          <ReactEChartsCore echarts={echarts} option={availOption} notMerge style={{ height: 200 }} />
        </section>
      </div>

      <section className="rounded-xl border border-rule bg-panel p-4" aria-labelledby="maint-h">
        <div className="flex flex-wrap items-end justify-between gap-3">
          <div>
            <h2 id="maint-h" className="text-[15px] font-semibold">
              Maintenance and cost
            </h2>
            <p className="mt-1 text-sm text-ink-2">
              {unplanned != null && (
                <>
                  Unplanned downtime cost{" "}
                  <span className="font-medium text-ink">{rupiah(unplanned * costPerMin)}</span> in this period (
                  {Math.round(unplanned)} min).{" "}
                </>
              )}
              {lead && (
                <>
                  Alerts warned on average{" "}
                  <span className="font-medium text-steel">{leadText(lead.avg)} before the stop</span> ({lead.count}{" "}
                  {lead.count === 1 ? "alert" : "alerts"}).{" "}
                </>
              )}
              Breakdowns are stops for mechanical, electrical or overheat reasons.
            </p>
          </div>
          <CostInput value={costPerMin} />
        </div>

        <div className="mt-3 overflow-x-auto">
          <table className="w-full min-w-[640px] text-left text-sm">
            <thead className="text-ink-2">
              <tr className="border-b border-rule">
                <th className="py-2 pr-4 font-medium">Machine</th>
                <th className="py-2 pr-4 text-right font-medium">Availability</th>
                <th className="py-2 pr-4 text-right font-medium">Unplanned downtime</th>
                <th className="py-2 pr-4 text-right font-medium">Cost</th>
                <th className="py-2 pr-4 text-right font-medium">Breakdowns</th>
                <th className="py-2 pr-4 text-right font-medium" title="Mean time to repair: average breakdown length">
                  MTTR
                </th>
                <th className="py-2 text-right font-medium" title="Mean time between failures: run time ÷ breakdowns">
                  MTBF
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-rule tabular-nums">
              {maint.map((m) => (
                <tr key={m.machine_id}>
                  <td className="py-2.5 pr-4">
                    <span className="font-medium">{m.machine_id.toUpperCase()}</span>{" "}
                    <span className="text-ink-2">{m.machine_name}</span>
                  </td>
                  <td className="py-2.5 pr-4 text-right">{pct(m.availability)}</td>
                  <td className="py-2.5 pr-4 text-right">{Math.round(m.downtimeMin)} min</td>
                  <td className="py-2.5 pr-4 text-right">{rupiah(m.downtimeMin * costPerMin)}</td>
                  <td className="py-2.5 pr-4 text-right">{m.breakdowns}</td>
                  <td className="py-2.5 pr-4 text-right">{m.mttrMin == null ? "–" : duration(m.mttrMin * 60)}</td>
                  <td className="py-2.5 text-right">{m.mtbfMin == null ? "–" : duration(m.mtbfMin * 60)}</td>
                </tr>
              ))}
              {!maint.length && (
                <tr>
                  <td colSpan={7} className="py-6 text-center text-ink-3">
                    Loading…
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}

function CostInput({ value }: { value: number }) {
  return (
    <label className="flex items-center gap-2 text-sm text-ink-2">
      Cost per minute of downtime
      <span className="flex items-center rounded-md border border-rule bg-panel focus-within:border-steel">
        <span className="pl-2 text-ink-3">Rp</span>
        <input
          type="number"
          min={0}
          step={1000}
          inputMode="numeric"
          value={value}
          onChange={(e) => setPrefs({ costPerMin: Math.max(0, Number(e.target.value) || 0) })}
          className="w-24 bg-transparent px-2 py-1 text-right tabular-nums text-ink outline-none"
          aria-label="Cost per minute of downtime, in Rupiah"
        />
      </span>
    </label>
  );
}
