"use client";

// Alert limits per machine: drag "normal" and "alert above" on one track per sensor.
// The backend scores |10-s average − normal| / scale and alerts at 3·scale, so a
// limit above normal implies the same distance below it (limit_low).

import { useState } from "react";
import { api } from "@/lib/api";
import type { LimitsUpdate, Machine, SensorKey } from "@/lib/types";

const SENSORS: { key: SensorKey; title: string; unit: string; step: number; digits: number }[] = [
  { key: "vib_rms", title: "Vibration", unit: "g RMS", step: 0.01, digits: 2 },
  { key: "current_a", title: "Current", unit: "A", step: 0.01, digits: 2 },
  { key: "temp_c", title: "Temperature", unit: "°C", step: 0.1, digits: 1 },
];

type Draft = Record<SensorKey, { normal: number; high: number }>;
type Scale = Record<SensorKey, { min: number; max: number }>;

const round = (v: number, step: number) => Math.round(v / step) * step;
const fix = (v: number, d: number) => Number(v.toFixed(d));

function niceStep(v: number) {
  const p = 10 ** Math.floor(Math.log10(v));
  return [1, 2, 2.5, 5, 10].map((m) => m * p).find((x) => x >= v)!;
}

/** Zoom the track around the band and the live reading so the thumbs are easy to grab. */
function scaleFor(d: Draft[SensorKey], live: number | null): { min: number; max: number } {
  const w = Math.max(d.high - d.normal, live != null ? Math.abs(live - d.normal) : 0, Math.abs(d.normal) * 0.05, 0.05);
  const tick = niceStep(w);
  const min = Math.max(0, Math.floor((Math.min(d.normal, live ?? d.normal) - 3 * w) / tick) * tick);
  const max = Math.ceil((Math.max(d.high, live ?? d.high) + 2.5 * w) / tick) * tick;
  return { min: Number(min.toPrecision(6)), max: Number(max.toPrecision(6)) };
}

function median(xs: number[]) {
  const s = [...xs].sort((a, b) => a - b);
  const m = s.length >> 1;
  return s.length % 2 ? s[m] : (s[m - 1] + s[m]) / 2;
}

export function LimitsEditor({ machine: m }: { machine: Machine }) {
  const [draft, setDraft] = useState<Draft | null>(null);
  const [scale, setScale] = useState<Scale | null>(null);
  const [busy, setBusy] = useState<"learn" | "save" | null>(null);
  const [note, setNote] = useState<{ tone: "ok" | "err" | "info"; text: string } | null>(null);

  const open = () => {
    const d = {} as Draft;
    const sc = {} as Scale;
    for (const s of SENSORS) {
      const b = m.baseline?.[s.key];
      const live = m.last?.[s.key] ?? null;
      const normal = b?.normal ?? live ?? 1;
      const high = b?.limit_high ?? normal * 1.3;
      d[s.key] = { normal: fix(normal, s.digits), high: fix(Math.max(high, normal + s.step), s.digits) };
      sc[s.key] = scaleFor(d[s.key], live);
    }
    setDraft(d);
    setScale(sc);
    setNote(null);
  };

  const set = (key: SensorKey, part: "normal" | "high", raw: number) => {
    if (!draft || !scale || Number.isNaN(raw)) return;
    const s = SENSORS.find((x) => x.key === key)!;
    const v = fix(round(raw, s.step), s.digits);
    const cur = draft[key];
    const next =
      part === "normal"
        ? { normal: Math.min(v, fix(cur.high - s.step, s.digits)), high: cur.high }
        : { normal: cur.normal, high: Math.max(v, fix(cur.normal + s.step, s.digits)) };
    setDraft({ ...draft, [key]: next });
    if (next.high > scale[key].max || next.normal < scale[key].min) setScale({ ...scale, [key]: scaleFor(next, m.last?.[key] ?? null) });
  };

  /** Same method as the backend's baseline tool: median, MAD × 1.4826 (at least 2 % of the median), limit at 3×. */
  const learn = async () => {
    if (!draft || !scale) return;
    setBusy("learn");
    setNote(null);
    try {
      const t = await api.telemetry(15, m.id);
      const all = (t.series[m.id] ?? []).filter((r) => r.current_a != null);
      const cur = median(all.map((r) => r.current_a!));
      const rows = all.filter((r) => r.current_a! > cur * 0.25); // leave out time the motor was stopped
      if (rows.length < 30) {
        setNote({ tone: "err", text: "Not enough running data in the last 15 minutes. Let the machine run normally, then try again." });
        return;
      }
      const d = { ...draft };
      const sc = { ...scale };
      for (const s of SENSORS) {
        const xs = rows.map((r) => r[s.key]).filter((x): x is number => x != null);
        if (xs.length < 30) continue;
        const med = median(xs);
        const spread = Math.max(median(xs.map((x) => Math.abs(x - med))) * 1.4826, Math.abs(med) * 0.02, s.step);
        d[s.key] = { normal: fix(med, s.digits), high: fix(Math.max(med + 3 * spread, med + s.step), s.digits) };
        sc[s.key] = scaleFor(d[s.key], m.last?.[s.key] ?? null);
      }
      setDraft(d);
      setScale(sc);
      setNote({ tone: "info", text: `Filled in from ${rows.length} readings over the last 15 minutes. Check the values, then save.` });
    } catch (e) {
      setNote({ tone: "err", text: e instanceof Error ? e.message : "Couldn't read the last 15 minutes." });
    } finally {
      setBusy(null);
    }
  };

  const save = async () => {
    if (!draft) return;
    setBusy("save");
    setNote(null);
    try {
      const body: LimitsUpdate = {};
      for (const s of SENSORS) body[s.key] = { normal: draft[s.key].normal, limit_high: draft[s.key].high };
      await api.setLimits(m.id, body);
      setDraft(null);
      setNote({ tone: "ok", text: "Saved. Alerts use the new limits within a minute." });
    } catch (e) {
      setNote({ tone: "err", text: e instanceof Error ? e.message : "Saving failed." });
    } finally {
      setBusy(null);
    }
  };

  return (
    <section className="rounded-xl border border-rule bg-panel p-4" aria-labelledby="limits-h">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 id="limits-h" className="text-[15px] font-semibold">
            Alert limits
          </h2>
          <p className="mt-0.5 max-w-[70ch] text-sm text-ink-2">
            What counts as normal for this machine. An alert is raised when the 10-second average stays outside the band for a
            few seconds.
          </p>
        </div>
        {!draft && (
          <button
            type="button"
            onClick={open}
            className="rounded-md border border-rule px-3 py-1.5 text-sm font-medium text-steel hover:border-steel"
          >
            Adjust limits
          </button>
        )}
      </div>

      {note && !draft && <Note {...note} />}

      {draft && scale && (
        <>
          <div className="mt-4 grid gap-4 lg:grid-cols-3">
            {SENSORS.map((s) => (
              <SensorLimit
                key={s.key}
                sensor={s}
                value={draft[s.key]}
                scale={scale[s.key]}
                live={m.online ? (m.last?.[s.key] ?? null) : null}
                saved={m.baseline?.[s.key]?.limit_high ?? null}
                onChange={(part, v) => set(s.key, part, v)}
              />
            ))}
          </div>

          {note && <Note {...note} />}

          <div className="mt-4 flex flex-wrap items-center gap-2 border-t border-rule pt-4">
            <button
              type="button"
              onClick={save}
              disabled={busy != null}
              className="rounded-md bg-steel px-4 py-1.5 text-sm font-medium text-white hover:bg-steel/90 disabled:opacity-60"
            >
              {busy === "save" ? "Saving…" : "Save limits"}
            </button>
            <button
              type="button"
              onClick={learn}
              disabled={busy != null}
              className="rounded-md border border-rule px-3 py-1.5 text-sm font-medium text-ink hover:border-ink-3 disabled:opacity-60"
              title="Use the median and spread of the last 15 minutes of running data"
            >
              {busy === "learn" ? "Reading…" : "Learn from last 15 min"}
            </button>
            <button
              type="button"
              onClick={() => {
                setDraft(null);
                setNote(null);
              }}
              className="px-3 py-1.5 text-sm text-ink-2 hover:text-ink"
            >
              Cancel
            </button>
          </div>
        </>
      )}
    </section>
  );
}

function Note({ tone, text }: { tone: "ok" | "err" | "info"; text: string }) {
  const c = tone === "err" ? "bg-alarm-tint text-alarm" : tone === "ok" ? "bg-paper text-ink" : "bg-steel/10 text-steel";
  return <p className={`mt-3 rounded-md px-3 py-2 text-sm ${c}`}>{text}</p>;
}

function SensorLimit({
  sensor: s,
  value,
  scale,
  live,
  saved,
  onChange,
}: {
  sensor: (typeof SENSORS)[number];
  value: { normal: number; high: number };
  scale: { min: number; max: number };
  live: number | null;
  saved: number | null;
  onChange: (part: "normal" | "high", v: number) => void;
}) {
  const span = scale.max - scale.min;
  const at = (v: number) => `${Math.min(Math.max((v - scale.min) / span, 0), 1) * 100}%`;
  const low = value.normal - (value.high - value.normal);
  const outside = live != null && (live > value.high || live < low);
  const f = (v: number) => v.toFixed(s.digits);

  return (
    <div className="rounded-lg border border-rule p-3">
      <div className="flex items-baseline justify-between gap-2">
        <h3 className="text-sm font-semibold">
          {s.title} <span className="font-normal text-ink-3">{s.unit}</span>
        </h3>
        {live != null && (
          <span className={`flex items-center gap-1 text-sm tabular-nums ${outside ? "font-medium text-warn" : "text-ink-2"}`}>
            <svg width="8" height="6" viewBox="0 0 10 7" className={outside ? "fill-warn" : "fill-ink"} aria-hidden="true">
              <path d="M0 0h10L5 7z" />
            </svg>
            now {f(live)}
          </span>
        )}
      </div>

      {/* track: the inner box is inset by the thumb radius so marks line up with thumb centres */}
      <div className="relative mt-4 h-7">
        <div className="absolute inset-x-[10px] top-1/2 h-2 -translate-y-1/2 rounded-full bg-warn-tint">
          <div
            className="absolute inset-y-0 rounded-full bg-[#dfe4ea]"
            style={{ left: at(Math.max(low, scale.min)), right: `calc(100% - ${at(value.high)})` }}
          />
          {saved != null && Math.abs(saved - value.high) > s.step / 2 && (
            <span
              className="absolute top-1/2 h-4 w-px -translate-y-1/2 bg-ink-3"
              style={{ left: at(saved) }}
              title={`Saved limit ${f(saved)}`}
            />
          )}
          {live != null && (
            <span
              className="absolute -top-[13px] -translate-x-1/2"
              style={{ left: at(live) }}
              title={`Now ${f(live)}`}
              aria-hidden="true"
            >
              <svg width="10" height="7" viewBox="0 0 10 7" className={outside ? "fill-warn" : "fill-ink"}>
                <path d="M0 0h10L5 7z" />
              </svg>
            </span>
          )}
        </div>
        <input
          type="range"
          className="gg-range"
          style={{ ["--thumb" as string]: "var(--color-ink-2)" }}
          min={scale.min}
          max={scale.max}
          step={s.step}
          value={value.normal}
          onChange={(e) => onChange("normal", Number(e.target.value))}
          aria-label={`${s.title} normal`}
        />
        <input
          type="range"
          className="gg-range"
          style={{ ["--thumb" as string]: "var(--color-warn)" }}
          min={scale.min}
          max={scale.max}
          step={s.step}
          value={value.high}
          onChange={(e) => onChange("high", Number(e.target.value))}
          aria-label={`${s.title} alert above`}
        />
      </div>
      <div className="flex justify-between px-[2px] text-[11px] tabular-nums text-ink-3">
        <span>{scale.min}</span>
        <span>{scale.max}</span>
      </div>

      <div className="mt-2 grid grid-cols-2 gap-2">
        <NumberField label="Normal" dot="bg-ink-2" value={value.normal} step={s.step} onChange={(v) => onChange("normal", v)} />
        <NumberField label="Alert above" dot="bg-warn" value={value.high} step={s.step} onChange={(v) => onChange("high", v)} />
      </div>

      <p className="mt-2 text-xs text-ink-2">
        Normal band {f(Math.max(low, 0))}–{f(value.high)}
        {low > 0 && <span className="text-ink-3"> (also alerts below {f(low)})</span>}
      </p>
      {live != null && (
        <p className={`mt-1 text-xs ${outside ? "font-medium text-warn" : "text-ink-3"}`}>
          {outside ? "With these limits the current reading would raise an alert." : "The current reading is inside the band."}
        </p>
      )}
    </div>
  );
}

function NumberField({
  label,
  dot,
  value,
  step,
  onChange,
}: {
  label: string;
  dot: string;
  value: number;
  step: number;
  onChange: (v: number) => void;
}) {
  const [text, setText] = useState<string | null>(null);
  return (
    <label className="block text-xs text-ink-2">
      <span className="flex items-center gap-1.5">
        <span className={`h-2 w-2 rounded-full ${dot}`} aria-hidden="true" />
        {label}
      </span>
      <input
        type="number"
        inputMode="decimal"
        step={step}
        min={0}
        value={text ?? String(value)}
        onChange={(e) => setText(e.target.value)}
        onBlur={() => {
          if (text != null && text.trim() !== "") onChange(Number(text));
          setText(null);
        }}
        onKeyDown={(e) => e.key === "Enter" && (e.target as HTMLInputElement).blur()}
        className="mt-1 w-full rounded-md border border-rule bg-panel px-2 py-1.5 text-sm tabular-nums text-ink focus:border-steel focus:outline-none"
      />
    </label>
  );
}
