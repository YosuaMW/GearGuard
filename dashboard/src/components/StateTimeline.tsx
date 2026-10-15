"use client";

// One row per machine across the selected window: running (grey),
// anomaly alerts (amber), unplanned stops (red), scheduled breaks (slate).
// Built only from /events and /alerts.

import ReactEChartsCore from "echarts-for-react/lib/core";
import * as echarts from "echarts/core";
import { CustomChart } from "echarts/charts";
import { GridComponent, TooltipComponent } from "echarts/components";
import { CanvasRenderer } from "echarts/renderers";
import { useMemo } from "react";
import { clock, duration } from "@/lib/format";
import { useWide } from "@/lib/useWide";
import type { Alert, StopEvent } from "@/lib/types";

echarts.use([CustomChart, GridComponent, TooltipComponent, CanvasRenderer]);

export const STATE_COLORS = {
  running: "#e3e7ec",
  anomaly: "#e0a43a",
  stopped: "#c0392b",
  planned: "#8796a8",
};

const KINDS = ["running", "anomaly", "stopped", "planned"] as const;

interface Bar {
  value: [number, number, number, number]; // row, start, end, kind index
  itemStyle: { color: string };
  kind: keyof typeof STATE_COLORS;
  text: string;
  z: number;
}

interface Props {
  machines: { id: string; name: string }[];
  events: StopEvent[];
  alerts: Alert[];
  start: string;
  end: string;
}

export function StateTimeline({ machines, events, alerts, start, end }: Props) {
  const wide = useWide();
  const option = useMemo(() => {
    const t0 = Date.parse(start);
    const t1 = Date.parse(end);
    const row = new Map(machines.map((m, i) => [m.id, i]));
    const bars: Bar[] = [];
    const clip = (a: number, b: number) => [Math.max(a, t0), Math.min(b, t1)] as const;

    machines.forEach((m, i) =>
      bars.push({ value: [i, t0, t1, 0], itemStyle: { color: STATE_COLORS.running }, kind: "running", text: "Running", z: 0 }),
    );
    for (const a of alerts) {
      const i = row.get(a.machine_id);
      if (i == null) continue;
      const [s, e] = clip(Date.parse(a.ts), a.resolved_ts ? Date.parse(a.resolved_ts) : t1);
      if (e > s) bars.push({ value: [i, s, e, 1], itemStyle: { color: STATE_COLORS.anomaly }, kind: "anomaly", text: a.title, z: 1 });
    }
    for (const ev of events) {
      const i = row.get(ev.machine_id);
      if (i == null) continue;
      const begin = Date.parse(ev.start_ts);
      // an ongoing stop runs to the right edge, even if it started a moment ago
      const [s, e] = clip(begin, ev.ongoing ? t1 : ev.end_ts ? Date.parse(ev.end_ts) : begin + ev.duration_s * 1000);
      if (e < s || s >= t1) continue;
      const planned = ev.category_id === "break";
      const text = ev.has_reason ? (ev.category ?? "Stopped") : ev.awaiting_reason ? "Stopped, waiting for operator" : "Stopped, no reason";
      bars.push({
        value: [i, s, Math.max(e, s + (t1 - t0) / 400), planned ? 3 : 2], // keep very short stops visible
        itemStyle: { color: planned ? STATE_COLORS.planned : STATE_COLORS.stopped },
        kind: planned ? "planned" : "stopped",
        text,
        z: 2,
      });
    }
    bars.sort((a, b) => a.z - b.z);

    return {
      animation: false,
      grid: { left: wide ? 112 : 36, right: 16, top: 8, bottom: 28 },
      tooltip: {
        formatter: (p: { data: Bar }) => {
          const [, s, e] = p.data.value;
          if (p.data.kind === "running") return "";
          return `<b>${machines[p.data.value[0]].id.toUpperCase()} · ${p.data.text}</b><br/>${clock(new Date(s).toISOString())}–${clock(new Date(e).toISOString())} WIB · ${duration((e - s) / 1000)}`;
        },
        textStyle: { fontFamily: "IBM Plex Sans", fontSize: 12 },
      },
      xAxis: {
        type: "time",
        min: t0,
        max: t1,
        axisLine: { lineStyle: { color: "#d5dae0" } },
        axisTick: { show: false },
        splitLine: { show: true, lineStyle: { color: "#eef0f3" } },
        axisLabel: {
          color: "#8a939d",
          fontSize: 11,
          fontFamily: "IBM Plex Sans",
          formatter: (v: number) => clock(new Date(v).toISOString()),
          hideOverlap: true,
        },
      },
      yAxis: {
        type: "category",
        inverse: true,
        data: machines.map((m) => (wide ? `${m.id.toUpperCase()}  ${m.name}` : m.id.toUpperCase())),
        axisLine: { show: false },
        axisTick: { show: false },
        axisLabel: { color: "#17202b", fontSize: 12, fontFamily: "IBM Plex Sans" },
      },
      series: [
        {
          type: "custom",
          encode: { x: [1, 2], y: 0 },
          // No hover highlight: it would lift a bar above the stops drawn on top of it.
          emphasis: { disabled: true },
          blur: { itemStyle: { opacity: 1 } },
          data: bars,
          renderItem: (
            params: { coordSys: { x: number; y: number; width: number; height: number } },
            api: {
              value: (i: number) => number;
              coord: (v: [number, number]) => [number, number];
              size: (v: [number, number]) => [number, number];
              style: () => Record<string, unknown>;
            },
          ) => {
            const r = api.value(0);
            const a = api.coord([api.value(1), r]);
            const b = api.coord([api.value(2), r]);
            const h = api.size([0, 1])[1] * 0.5;
            const shape = echarts.graphic.clipRectByRect(
              { x: a[0], y: a[1] - h / 2, width: Math.max(b[0] - a[0], 1), height: h },
              params.coordSys,
            );
            const running = KINDS[api.value(3)] === "running";
            // The grey "running" background never reacts to the cursor, so it can't cover a stop.
            return shape && { type: "rect", shape: { ...shape, r: 2 }, style: api.style(), silent: running };
          },
        },
      ],
    };
  }, [machines, events, alerts, start, end, wide]);

  return (
    <div>
      <ReactEChartsCore echarts={echarts} option={option} lazyUpdate style={{ height: 40 + machines.length * 44 }} />
      <ul className="mt-1 flex flex-wrap gap-x-5 gap-y-1 text-xs text-ink-2">
        {(
          [
            ["running", "Running"],
            ["anomaly", "Anomaly alert"],
            ["stopped", "Unplanned stop"],
            ["planned", "Scheduled break"],
          ] as const
        ).map(([k, label]) => (
          <li key={k} className="flex items-center gap-1.5">
            <span className="h-2.5 w-4 rounded-sm" style={{ background: STATE_COLORS[k] }} aria-hidden="true" />
            {label}
          </li>
        ))}
      </ul>
    </div>
  );
}
