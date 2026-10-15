"use client";

import { api } from "@/lib/api";
import { clock } from "@/lib/format";
import { usePolling } from "@/lib/usePolling";

export default function AmdPage() {
  const usage = usePolling(api.aiUsage, 10_000).data;
  const onAmd = usage?.mode === "amd";
  const llm = usage?.endpoints.find((e) => e.endpoint !== "/transcribe" && e.mock === false && e.model)?.model ?? "Qwen3.8-27B";

  return (
    <div className="space-y-5">
      <header>
        <h1 className="text-2xl font-semibold tracking-tight">Running on AMD</h1>
        <p className="mt-1 max-w-[75ch] text-sm text-ink">
          Speech-to-text runs on the edge gateway (Raspberry Pi); classification and alert explanations run on AMD
          Token Factory ({llm}).
        </p>
        <p className="mt-1 max-w-[75ch] text-sm text-ink-2">
          Token Factory serves language models but not audio, so Whisper transcribes voice notes on the Pi next to the
          line. Every call the backend makes is logged below.
        </p>
      </header>

      {usage && !onAmd && (
        <p className="rounded-xl border border-rule bg-panel px-4 py-3 text-sm text-ink-2">
          The backend isn&apos;t connected to AMD yet, so these steps run on placeholder rules.
        </p>
      )}

      <section className="overflow-x-auto rounded-xl border border-rule bg-panel">
        <table className="w-full min-w-[760px] text-left text-sm">
          <thead className="bg-paper text-ink-2">
            <tr>
              <th className="px-4 py-2.5 font-medium">What the AI does</th>
              <th className="px-4 py-2.5 font-medium">Runs on</th>
              <th className="px-4 py-2.5 font-medium">Model</th>
              <th className="px-4 py-2.5 text-right font-medium">Calls today</th>
              <th className="px-4 py-2.5 text-right font-medium">Avg latency</th>
              <th className="px-4 py-2.5 text-right font-medium">Success</th>
              <th className="px-4 py-2.5 text-right font-medium">Last call</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-rule">
            {(usage?.endpoints ?? []).map((e) => {
              const pending = e.mock !== false || e.calls_today === 0;
              return (
                <tr key={e.endpoint}>
                  <td className="px-4 py-3">
                    {e.description}
                    <span className="block text-xs text-ink-3">{e.endpoint}</span>
                  </td>
                  <td className="px-4 py-3">
                    {e.endpoint === "/transcribe" ? (
                      <span className="text-ink-2">Raspberry Pi (edge)</span>
                    ) : (
                      <span className="font-medium text-steel">AMD Token Factory</span>
                    )}
                  </td>
                  <td className={`px-4 py-3 ${pending ? "text-ink-3" : ""}`}>
                    {pending ? "To be confirmed by role 3" : e.model}
                  </td>
                  <td className="px-4 py-3 text-right tabular-nums">{e.calls_today}</td>
                  <td className="px-4 py-3 text-right tabular-nums">
                    {e.avg_latency_ms == null
                      ? "–"
                      : e.avg_latency_ms < 1000
                        ? `${e.avg_latency_ms} ms`
                        : `${(e.avg_latency_ms / 1000).toFixed(1)} s`}
                  </td>
                  <td className="px-4 py-3 text-right tabular-nums">
                    {e.success_rate != null ? `${Math.round(e.success_rate * 100)}%` : "–"}
                  </td>
                  <td className="px-4 py-3 text-right tabular-nums text-ink-2">{e.last_call ? clock(e.last_call) : "–"}</td>
                </tr>
              );
            })}
            {!usage && (
              <tr>
                <td colSpan={7} className="px-4 py-6 text-center text-ink-2">
                  Loading AI usage…
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </section>
    </div>
  );
}
