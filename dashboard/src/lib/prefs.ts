"use client";

// Small per-browser settings (downtime cost, notification sound).
// Kept in localStorage when available; the app works the same without it.

import { useSyncExternalStore } from "react";

const DEFAULT_COST = Number(process.env.NEXT_PUBLIC_DOWNTIME_COST_PER_MIN ?? 15000);

interface Prefs {
  costPerMin: number; // Rupiah per minute of unplanned downtime, for the whole line
  sound: boolean;
}

const KEY = "gearguard.prefs";
let prefs: Prefs = { costPerMin: DEFAULT_COST, sound: false };
let loaded = false;
const listeners = new Set<() => void>();

function load() {
  if (loaded || typeof window === "undefined") return;
  loaded = true;
  try {
    const raw = window.localStorage.getItem(KEY);
    if (raw) prefs = { ...prefs, ...JSON.parse(raw) };
  } catch {
    /* storage unavailable: keep defaults */
  }
}

export function setPrefs(patch: Partial<Prefs>) {
  load();
  prefs = { ...prefs, ...patch };
  try {
    window.localStorage.setItem(KEY, JSON.stringify(prefs));
  } catch {
    /* ignore */
  }
  listeners.forEach((l) => l());
}

const SERVER: Prefs = { costPerMin: DEFAULT_COST, sound: false };

export function usePrefs(): Prefs {
  return useSyncExternalStore(
    (l) => {
      listeners.add(l);
      return () => listeners.delete(l);
    },
    () => {
      load();
      return prefs;
    },
    () => SERVER,
  );
}

const idr = new Intl.NumberFormat("id-ID", { style: "currency", currency: "IDR", maximumFractionDigits: 0 });

/** Rp 1.250.000 → "Rp 1,25 jt" for tight spaces; full amount otherwise. */
export function rupiah(amount: number, compact = false) {
  if (!compact || amount < 1_000_000) return idr.format(Math.round(amount));
  return `Rp ${(amount / 1_000_000).toLocaleString("id-ID", { maximumFractionDigits: 2 })} jt`;
}
