"use client";

import { useEffect, useRef, useState } from "react";

/**
 * Calls `fetcher` now and then every `intervalMs`. Skips a tick if the previous
 * call is still running, so a slow backend never piles up requests. Keeps the
 * last good data when a call fails, so the screen doesn't go blank on one hiccup.
 *
 * `fetcher` must be stable (module-level or useCallback). When it changes, for
 * example a new time range, polling restarts immediately with the new one.
 */
export function usePolling<T>(fetcher: () => Promise<T>, intervalMs: number) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [lastOk, setLastOk] = useState<number | null>(null);
  const busy = useRef(false);

  useEffect(() => {
    let alive = true;
    busy.current = false;
    const tick = async () => {
      if (busy.current) return;
      busy.current = true;
      try {
        const next = await fetcher();
        if (alive) {
          setData(next);
          setError(null);
          setLastOk(Date.now());
        }
      } catch (e) {
        if (alive) setError(e instanceof Error ? e.message : String(e));
      } finally {
        if (alive) busy.current = false;
      }
    };
    tick();
    const timer = setInterval(tick, intervalMs);
    return () => {
      alive = false;
      clearInterval(timer);
    };
  }, [fetcher, intervalMs]);

  return { data, error, lastOk };
}
