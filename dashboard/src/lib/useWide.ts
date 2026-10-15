"use client";

import { useSyncExternalStore } from "react";

const QUERY = "(min-width: 640px)";

/** True on tablet/desktop widths; charts use it to shorten labels on phones. */
export function useWide() {
  return useSyncExternalStore(
    (cb) => {
      const m = window.matchMedia(QUERY);
      m.addEventListener("change", cb);
      return () => m.removeEventListener("change", cb);
    },
    () => window.matchMedia(QUERY).matches,
    () => true,
  );
}
