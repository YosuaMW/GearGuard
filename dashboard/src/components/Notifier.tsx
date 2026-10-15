"use client";

// Pops a short notice when something new happens on the line:
// an anomaly alert, a machine stopping, or an operator's reason arriving.
// What already exists when the page loads is not announced.

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { usePlant } from "@/lib/plant";
import { usePrefs } from "@/lib/prefs";

type Tone = "warn" | "alarm" | "info";
interface Notice {
  key: string;
  tone: Tone;
  title: string;
  detail?: string;
  href: string;
}

const LIFETIME_MS = 7000;
const MAX_VISIBLE = 4;

function beep(tone: Tone) {
  try {
    const Ctx = window.AudioContext ?? (window as unknown as { webkitAudioContext: typeof AudioContext }).webkitAudioContext;
    const ctx = new Ctx();
    const notes = tone === "alarm" ? [880, 660] : tone === "warn" ? [740, 740] : [660];
    notes.forEach((f, i) => {
      const o = ctx.createOscillator();
      const g = ctx.createGain();
      o.frequency.value = f;
      o.type = "sine";
      const t = ctx.currentTime + i * 0.18;
      g.gain.setValueAtTime(0.0001, t);
      g.gain.exponentialRampToValueAtTime(0.15, t + 0.02);
      g.gain.exponentialRampToValueAtTime(0.0001, t + 0.15);
      o.connect(g).connect(ctx.destination);
      o.start(t);
      o.stop(t + 0.16);
    });
    setTimeout(() => ctx.close(), 800);
  } catch {
    /* audio blocked or unsupported */
  }
}

export function Notifier() {
  const { alerts, events } = usePlant();
  const { sound } = usePrefs();
  const [notices, setNotices] = useState<Notice[]>([]);
  const seen = useRef<Set<string> | null>(null);
  const soundRef = useRef(sound);

  useEffect(() => {
    soundRef.current = sound;
  }, [sound]);

  useEffect(() => {
    if (!alerts || !events) return;
    const keys: [string, () => Notice][] = [];
    for (const a of alerts) {
      if (a.active)
        keys.push([
          `alert-${a.id}`,
          () => ({
            key: `alert-${a.id}`,
            tone: "warn",
            title: `${a.machine_id.toUpperCase()} · ${a.title}`,
            detail: "Predictive alert",
            href: `/machines/${a.machine_id}/`,
          }),
        ]);
    }
    for (const e of events) {
      keys.push([
        `stop-${e.id}`,
        () => ({
          key: `stop-${e.id}`,
          tone: "alarm",
          title: `${e.machine_id.toUpperCase()} ${e.machine_name} stopped`,
          detail: e.awaiting_reason ? "Bot is asking the operator why" : undefined,
          href: `/machines/${e.machine_id}/`,
        }),
      ]);
      if (e.has_reason)
        keys.push([
          `reason-${e.id}`,
          () => ({
            key: `reason-${e.id}`,
            tone: "info",
            title: `${e.machine_id.toUpperCase()} reason: ${e.needs_review ? "Needs review" : e.category}`,
            detail: e.transcript ? `“${e.transcript}”` : undefined,
            href: `/machines/${e.machine_id}/`,
          }),
        ]);
    }

    // First data after page load: remember it, announce nothing.
    if (!seen.current) {
      seen.current = new Set(keys.map(([k]) => k));
      return;
    }
    const fresh = keys.filter(([k]) => !seen.current!.has(k)).map(([k, make]) => {
      seen.current!.add(k);
      return make();
    });
    if (!fresh.length) return;
    // Replay reasons arrive together with the stop; show only the newer, more useful one.
    const shown = fresh.filter(
      (n) => !(n.key.startsWith("stop-") && fresh.some((m) => m.key === `reason-${n.key.slice(5)}`)),
    );
    if (soundRef.current) beep(shown.some((n) => n.tone === "alarm") ? "alarm" : shown[0].tone);
    setNotices((cur) => [...shown, ...cur].slice(0, MAX_VISIBLE));
    for (const n of shown) setTimeout(() => setNotices((cur) => cur.filter((x) => x.key !== n.key)), LIFETIME_MS);
  }, [alerts, events]);

  return (
    <div
      aria-live="polite"
      className="pointer-events-none fixed bottom-4 right-4 z-50 flex w-[min(360px,calc(100vw-2rem))] flex-col gap-2"
    >
      {notices.map((n) => (
        <Link
          key={n.key}
          href={n.href}
          className={`toast-in pointer-events-auto rounded-lg border bg-panel px-4 py-3 shadow-lg ${
            n.tone === "alarm" ? "border-alarm" : n.tone === "warn" ? "border-warn" : "border-rule"
          }`}
        >
          <p
            className={`text-sm font-medium ${n.tone === "alarm" ? "text-alarm" : n.tone === "warn" ? "text-warn" : "text-ink"}`}
          >
            {n.title}
          </p>
          {n.detail && (
            <p className="mt-0.5 truncate text-xs text-ink-2" lang={n.tone === "info" ? "id" : undefined}>
              {n.detail}
            </p>
          )}
        </Link>
      ))}
    </div>
  );
}
