"use client";

import Link from "next/link";
import { clock, num } from "@/lib/format";
import { leadSeconds, leadText } from "@/lib/leadtime";
import { usePlant } from "@/lib/plant";
import type { Alert } from "@/lib/types";

const AI_WAIT_S = 90; // the AI explanation usually lands 30–50 s after the alert

export function sourceText(s: Alert["sources"][number]) {
  return s.page != null ? `${s.title}, p. ${s.page}` : s.title;
}

/** Fallback when /ai-usage hasn't reported a model yet. */
const DEFAULT_MODEL = "Qwen";

function shortModel(model: string | null) {
  if (!model) return DEFAULT_MODEL;
  return model.split(/[-_ ]/)[0] || model; // "Qwen3.8-27B" → "Qwen3.8"
}

/** Who wrote the explanation: the LLM on AMD, or the backend's rules. */
export function ExplanationBadge({ alert }: { alert: Alert }) {
  const { explainModel } = usePlant();
  if (alert.explanation_source === "ai")
    return (
      <span
        className="inline-flex items-center gap-1 rounded bg-steel/10 px-1.5 py-0.5 text-[11px] font-medium text-steel"
        title={explainModel ? `${explainModel} on AMD Token Factory` : "LLM on AMD Token Factory"}
      >
        <SparkIcon /> AI · {shortModel(explainModel)} on AMD
      </span>
    );
  return <span className="rounded bg-paper px-1.5 py-0.5 text-[11px] font-medium text-ink-2">Rule-based</span>;
}

/** Full explanation, its source, the manual pages to check and the sensor evidence. */
export function AlertExplanation({ alert }: { alert: Alert }) {
  const { summary, lastOk } = usePlant();
  const ageS = ((lastOk ?? 0) - Date.parse(alert.ts)) / 1000; // lastOk ticks every second with /machines
  const waitingForAi =
    alert.active && alert.explanation_source !== "ai" && summary?.ai_mode === "amd" && ageS < AI_WAIT_S;

  return (
    <>
      <div className="mt-1.5 flex flex-wrap items-center gap-2">
        <ExplanationBadge alert={alert} />
        {waitingForAi && <span className="text-[11px] text-ink-3">AI explanation on the way…</span>}
      </div>
      <p className="mt-1.5 whitespace-pre-line text-sm leading-relaxed text-ink">{alert.explanation}</p>
      {alert.sources.length > 0 && (
        <p className="mt-2 text-xs text-ink-2">
          <span className="font-medium text-ink">Check:</span>{" "}
          {alert.sources.map((s, i) => (
            <span key={i} title={s.snippet}>
              {i > 0 && "; "}
              {sourceText(s)}
            </span>
          ))}
        </p>
      )}
      <Evidence alert={alert} />
    </>
  );
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
  const { events } = usePlant();
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
            <AlertExplanation alert={a} />
          </li>
        ))}
      </ul>

      {recent.length > 0 && (
        <>
          <h3 className="mt-4 text-xs font-medium text-ink-2">Resolved today</h3>
          <ul className="mt-1.5 space-y-1.5 text-sm text-ink-2">
            {recent.map((a) => {
              const lead = leadSeconds(a, events);
              return (
                <li key={a.id}>
                  <div className="flex justify-between gap-2">
                    <span className="truncate">
                      {a.machine_id.toUpperCase()} · {a.title}
                    </span>
                    <span className="shrink-0 text-xs">{clock(a.ts)}</span>
                  </div>
                  {lead != null && (
                    <p className="text-xs font-medium text-steel">Warned {leadText(lead)} before the stop</p>
                  )}
                </li>
              );
            })}
          </ul>
        </>
      )}
    </section>
  );
}

function SparkIcon() {
  return (
    <svg width="11" height="11" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
      <path d="M12 2l2.2 6.3L20.5 10l-6.3 2.2L12 18.5l-2.2-6.3L3.5 10l6.3-1.7z" />
    </svg>
  );
}
