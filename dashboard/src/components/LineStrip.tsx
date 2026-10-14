"use client";

import Link from "next/link";
import type { Machine } from "@/lib/types";
import { condition } from "./MachineStatus";

/**
 * The production line drawn as a schematic: four stations on one conveyor.
 * Normal stations stay grey; only abnormal ones take colour.
 */
export function LineStrip({ machines }: { machines: Machine[] }) {
  return (
    <section aria-label="Production line" className="rounded-xl border border-rule bg-panel px-4 py-5 sm:px-6">
      <div className="relative">
        <div className="absolute left-8 right-8 top-[27px] h-[3px] rounded bg-rule" aria-hidden="true" />
        <ol className="relative grid grid-cols-4 gap-2">
          {machines.map((m) => {
            const c = condition(m);
            const tone =
              c.kind === "stopped"
                ? "border-alarm bg-alarm text-white"
                : c.kind === "anomaly"
                  ? "border-warn bg-warn-tint text-warn"
                  : c.kind === "offline"
                    ? "border-dashed border-ink-3 bg-paper text-ink-3"
                    : "border-ink-3 bg-panel text-ink";
            const pulse = m.awaiting_reason ? "alarm-breathe" : c.kind === "anomaly" ? "warn-breathe" : "";
            return (
              <li key={m.id} className="flex flex-col items-center text-center">
                <Link
                  href={`/machines/${m.id}/`}
                  className={`flex h-14 w-14 items-center justify-center rounded-lg border-2 text-[15px] font-semibold transition-colors duration-500 ${tone} ${pulse}`}
                  aria-label={`${m.id.toUpperCase()} ${m.name}, ${c.text}`}
                >
                  {m.id.toUpperCase()}
                </Link>
                <span className="mt-2 text-sm font-medium">{m.name}</span>
                <span className={`text-xs ${c.tone}`}>{c.text}</span>
              </li>
            );
          })}
        </ol>
      </div>
    </section>
  );
}
