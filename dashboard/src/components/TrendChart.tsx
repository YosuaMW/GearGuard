"use client";

import ReactEChartsCore from "echarts-for-react/lib/core";
import * as echarts from "echarts/core";
import { LineChart } from "echarts/charts";
import { GridComponent, MarkLineComponent, TooltipComponent } from "echarts/components";
import { CanvasRenderer } from "echarts/renderers";
import { useMemo } from "react";

echarts.use([LineChart, GridComponent, MarkLineComponent, TooltipComponent, CanvasRenderer]);

const INK_3 = "#8a939d";
const RULE = "#d5dae0";

interface Props {
  values: (number | null)[];
  times?: string[];
  color?: string;
  height: number;
  /** Draws a dashed limit line, e.g. the alert threshold. */
  limit?: number;
  /** Full chart with axes; otherwise a bare sparkline. */
  detailed?: boolean;
  unit?: string;
  min?: number;
  max?: number;
}

/** Axis bounds on round numbers that always include the alert limit. */
function niceRange(values: (number | null)[], limit: number | undefined, min?: number, max?: number) {
  const nums = values.filter((v): v is number => v != null);
  if (limit != null) nums.push(limit);
  if (!nums.length) return { min: min ?? 0, max: max ?? 1 };
  let lo = min ?? Math.min(...nums);
  let hi = max ?? Math.max(...nums);
  if (hi - lo < 1e-6) hi = lo + 1;
  const raw = (hi - lo) / 4;
  const mag = 10 ** Math.floor(Math.log10(raw));
  const step = [1, 2, 2.5, 5, 10].map((k) => k * mag).find((s) => s >= raw) ?? 10 * mag;
  if (min == null) lo = Math.floor(lo / step) * step;
  if (max == null) hi = Math.ceil((hi + step * 0.25) / step) * step;
  return { min: Math.round(lo * 1e6) / 1e6, max: Math.round(hi * 1e6) / 1e6, interval: step };
}

export function TrendChart({ values, times, color = INK_3, height, limit, detailed, unit = "", min, max }: Props) {
  const option = useMemo(() => {
    const y = niceRange(values, limit, min, max);
    return {
      animation: false,
      grid: detailed
        ? { left: 44, right: 12, top: 12, bottom: 24 }
        : { left: 0, right: 0, top: 2, bottom: 2 },
      tooltip: detailed
        ? { trigger: "axis", valueFormatter: (v: number) => `${v} ${unit}`, textStyle: { fontFamily: "IBM Plex Sans" } }
        : undefined,
      xAxis: {
        type: "category",
        show: !!detailed,
        data: times ?? values.map((_, i) => i),
        boundaryGap: false,
        axisLine: { lineStyle: { color: RULE } },
        axisTick: { show: false },
        axisLabel: { color: INK_3, fontSize: 11, interval: 29, fontFamily: "IBM Plex Sans" },
      },
      yAxis: {
        type: "value",
        show: !!detailed,
        min: y.min,
        max: y.max,
        interval: detailed ? y.interval : undefined,
        splitLine: { lineStyle: { color: "#eef0f3" } },
        axisLabel: { color: INK_3, fontSize: 11, fontFamily: "IBM Plex Sans" },
      },
      series: [
        {
          type: "line",
          data: values,
          showSymbol: false,
          connectNulls: false,
          smooth: 0.3,
          lineStyle: { width: detailed ? 2 : 1.5, color },
          areaStyle: detailed ? { color, opacity: 0.06 } : undefined,
          markLine:
            limit != null
              ? {
                  symbol: "none",
                  silent: true,
                  lineStyle: { color: "#b8770a", type: "dashed", width: 1 },
                  label: detailed
                    ? { formatter: "Alert limit", color: "#b8770a", fontSize: 11, position: "insideEndTop" }
                    : { show: false },
                  data: [{ yAxis: limit }],
                }
              : undefined,
        },
      ],
    };
  }, [values, times, color, detailed, limit, unit, min, max]);

  return (
    <ReactEChartsCore
      echarts={echarts}
      option={option}
      notMerge={false}
      lazyUpdate
      style={{ height, width: "100%" }}
      opts={{ renderer: "canvas" }}
    />
  );
}
