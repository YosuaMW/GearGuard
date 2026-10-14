"use client";

import Link from "next/link";
import { clock, num } from "@/lib/format";
import type { Alert } from "@/lib/types";

export function sourceText(s: Alert["sources"][number]) {
  return s.page != null ? `${s.title}, p. ${s.page}` : s.title;
}

/** "Vibration 0.62 g RMS (normal 0.40)" for the sensors that drove the alert. */
export function Evidence({ alert }: { alert: Alert }) {
  const feats = Object.entries(alert.features ?? {}).filter(([, f]) => f && f.now != null);
  if (!feats.length) return null;
  const digits = (key: string) => (key === "temp_c" ? 1 : 2);
  return (
    <ul className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-xs text-ink-2">
      {feats.map(([key, f]) => (
        <li key={key}>
          {f!.label} <span className="font-medium tabular-nums text-ink">{num(f!.now, digits(key))}</span> {f!.unit}
          {f!.normal != null && <span> (normal {num(f!.normal, digits(key))})</span>}
        </li>
      ))}
    </ul>
  );
}

export function AlertPanel({ alerts }: { alerts: Alert[] | null }) {
  const active = alerts?.filter((a) => a.active) ?? [];
  const recent = alerts?.filter((a) => !a.active).slice(0, 3) ?? [];

  return (
    <section className="rounded-xl border border-rule bg-panel p-4" aria-labelledby="alerts-h">
      <h2 id="alerts-h" className="flex items-center justify-between text-[15px] font-semibold">
        Predictive alerts
        {active.length > 0 && (
          <span className="rounded-md bg-warn-tint px-2 py-0.5 text-sm font-medium text-warn">{active.length} active</span>
        )}
      </h2>

      {active.length === 0 && (
        <p className="mt-3 text-sm text-ink-2">
          No machine is drifting from its normal pattern. New alerts appear here with an explanation and the manual
          page to check.
        </p>
      )}

      <ul className="mt-3 space-y-3">
        {active.map((a) => (
          <li key={a.id} className="rounded-lg border border-warn/40 bg-warn-tint/50 p-3">
            <div className="flex items-baseline justify-between gap-2">
              <Link href={`/machines/${a.machine_id}/`} className="font-medium hover:underline">
                {a.machine_id.toUpperCase()} · {a.title}
              </Link>
              <span className="shrink-0 text-xs text-ink-2">{clock(a.ts)}</span>
            </div>
            <p className="mt-1.5 text-sm leading-relaxed text-ink">{a.explanation}</p>
            <Evidence alert={a} />
            {a.sources.length > 0 && (
              <ul className="mt-2 flex flex-wrap gap-1.5">
                {a.sources.map((s, i) => (
                  <li key={i} className="rounded border border-rule bg-panel px-2 py-0.5 text-xs text-ink-2" title={s.snippet}>
                    {sourceText(s)}
                  </li>
                ))}
              </ul>
            )}
          </li>
        ))}
      </ul>

      {recent.length > 0 && (
        <>
          <h3 className="mt-4 text-xs font-medium text-ink-2">Resolved today</h3>
          <ul className="mt-1.5 space-y-1 text-sm text-ink-2">
            {recent.map((a) => (
              <li key={a.id} className="flex justify-between gap-2">
                <span className="truncate">
                  {a.machine_id.toUpperCase()} · {a.title}
                </span>
                <span className="shrink-0 text-xs">{clock(a.ts)}</span>
              </li>
            ))}
          </ul>
        </>
      )}
    </section>
  );
}
