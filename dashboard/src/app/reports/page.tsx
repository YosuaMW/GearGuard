"use client";

import ReactEChartsCore from "echarts-for-react/lib/core";
import * as echarts from "echarts/core";
import { BarChart, LineChart } from "echarts/charts";
import { GridComponent, TooltipComponent } from "echarts/components";
import { CanvasRenderer } from "echarts/renderers";
import { useCallback, useState } from "react";
import { api } from "@/lib/api";
import { pct } from "@/lib/format";
import type { Range } from "@/lib/types";
import { usePolling } from "@/lib/usePolling";

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
  const pareto = usePolling(fetchPareto, 10_000).data;
  const avail = usePolling(fetchAvail, 10_000).data;

  const cats = pareto?.window.range === range ? pareto.categories : [];
  const machines = avail?.window.range === range ? avail.machines : [];

  const paretoOption = {
    animationDuration: 400,
    grid: { left: 48, right: 44, top: 32, bottom: 72 },
    tooltip: { trigger: "axis", textStyle: { fontFamily: "IBM Plex Sans" } },
    xAxis: {
      type: "category",
      data: cats.map((p) => p.category),
      axisLabel: { ...FONT, interval: 0, width: 90, overflow: "break" },
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
    </div>
  );
}
