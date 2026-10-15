"use client";

import { AlertPanel } from "@/components/AlertPanel";
import { EventList } from "@/components/EventList";
import { LineStrip } from "@/components/LineStrip";
import { MachineCard } from "@/components/MachineCard";
import { api } from "@/lib/api";
import { pct } from "@/lib/format";
import { unplannedMinutes } from "@/lib/maintenance";
import { usePlant } from "@/lib/plant";
import { rupiah, usePrefs } from "@/lib/prefs";
import { usePolling } from "@/lib/usePolling";

const fetchShiftAvailability = () => api.availability("shift");

export default function OverviewPage() {
  const { machines, alerts, events, telemetry, summary, error } = usePlant();
  const avail = usePolling(fetchShiftAvailability, 10_000).data;
  const { costPerMin } = usePrefs();

  if (!machines) {
    return (
      <p className="py-20 text-center text-ink-2">
        {error ? `Can't reach the line server (${error}). Retrying every second.` : "Connecting to the line…"}
      </p>
    );
  }

  const unplanned = unplannedMinutes(avail);
  const activeAlerts = summary?.active_alerts ?? 0;
  const noReason = summary?.stops_without_reason ?? 0;

  return (
    <div className="space-y-5">
      <LineStrip machines={machines} />

      <section aria-label="Shift summary" className="overflow-hidden rounded-xl border border-rule bg-panel">
        <div className="grid grid-cols-2 md:grid-cols-4">
          <Summary label="Availability" value={summary ? pct(summary.availability) : "–"} />
          <Summary
            label="Downtime"
            value={summary?.downtime_minutes != null ? `${Math.round(summary.downtime_minutes)} min` : "–"}
            note={unplanned != null ? `Unplanned cost ≈ ${rupiah(unplanned * costPerMin, true)}` : undefined}
          />
          <Summary label="Active alerts" value={summary ? String(activeAlerts) : "–"} tone={activeAlerts ? "warn" : undefined} />
          <Summary label="Stops without a reason" value={summary ? String(noReason) : "–"} tone={noReason ? "alarm" : undefined} />
        </div>
        {summary && <p className="border-t border-rule px-4 py-2 text-xs text-ink-3">{summary.window.label} WIB</p>}
      </section>

      <div className="grid gap-5 lg:grid-cols-[minmax(0,2fr)_minmax(0,1fr)]">
        <section aria-label="Machines" className="grid content-start items-start gap-4 sm:grid-cols-2">
          {machines.map((m) => (
            <MachineCard key={m.id} machine={m} series={telemetry?.series[m.id] ?? []} />
          ))}
        </section>

        <div className="space-y-5">
          <AlertPanel alerts={alerts} />
          <section className="rounded-xl border border-rule bg-panel p-4" aria-labelledby="events-h">
            <h2 id="events-h" className="text-[15px] font-semibold">
              Today on the line
            </h2>
            <div className="mt-1">
              <EventList events={events} alerts={alerts} limit={8} />
            </div>
          </section>
        </div>
      </div>
    </div>
  );
}

function Summary({ label, value, tone, note }: { label: string; value: string; tone?: "warn" | "alarm"; note?: string }) {
  const color = tone === "alarm" ? "text-alarm" : tone === "warn" ? "text-warn" : "text-ink";
  return (
    <div className="border-rule p-4 [&:nth-child(2)]:border-l [&:nth-child(4)]:border-l [&:nth-child(n+3)]:border-t md:[&:nth-child(n+2)]:border-l md:[&:nth-child(n+3)]:border-t-0">
      <p className="text-sm text-ink-2">{label}</p>
      <p className={`mt-1 text-[28px] font-medium leading-none tabular-nums ${color}`}>{value}</p>
      {note && <p className="mt-1.5 text-xs text-ink-2">{note}</p>}
    </div>
  );
}
