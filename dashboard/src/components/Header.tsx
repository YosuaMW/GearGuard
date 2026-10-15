"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import { USING_SIMULATOR } from "@/lib/api";
import { nowWib } from "@/lib/format";
import { usePlant } from "@/lib/plant";
import { setPrefs, usePrefs } from "@/lib/prefs";

const NAV = [
  { href: "/", label: "Overview" },
  { href: "/machines/m1/", label: "Machines" },
  { href: "/reports/", label: "Reports" },
  { href: "/amd/", label: "Running on AMD" },
];

function isActive(path: string, href: string) {
  if (href === "/") return path === "/";
  return path.startsWith(href.split("/").slice(0, 2).join("/"));
}

/** What the badge says about where the numbers come from. */
function dataBadge(lost: boolean, mode: string | undefined) {
  if (lost) return { text: "Connection lost", dot: "bg-alarm" };
  if (USING_SIMULATOR) return { text: "Demo data (offline)", dot: "bg-ink-3" };
  if (mode === "live") return { text: "Live data · M1", dot: "bg-run" };
  if (mode === "replay") return { text: "Simulated data", dot: "bg-ink-3" };
  if (mode === "offline") return { text: "No machine sending data", dot: "bg-warn" };
  return { text: "Connecting…", dot: "bg-ink-3" };
}

export function Header() {
  const path = usePathname();
  const { error, lastOk, summary } = usePlant();
  const [now, setNow] = useState("");
  const [stale, setStale] = useState(false);

  useEffect(() => {
    const t = () => {
      setNow(nowWib());
      setStale(lastOk ? Date.now() - lastOk > 5000 : false);
    };
    t();
    const id = setInterval(t, 1000);
    return () => clearInterval(id);
  }, [lastOk]);

  const badge = dataBadge(!!error || stale, summary?.data_mode);
  const { sound } = usePrefs();

  return (
    <header className="mb-5 border-b border-rule bg-panel">
      <div className="mx-auto flex max-w-[1280px] flex-wrap items-center gap-x-8 gap-y-2 px-4 py-3 sm:px-6">
        <Link href="/" className="flex items-center gap-2.5">
          {/* eslint-disable-next-line @next/next/no-img-element -- static SVG logo */}
          <img src="/brand/gearguard-logo.svg" alt="GearGuard" width={135} height={30} />
          <span className="text-sm text-ink-2">Line A</span>
        </Link>

        <nav className="order-3 -mx-1 flex w-full gap-1 overflow-x-auto sm:order-none sm:w-auto">
          {NAV.map((n) => {
            const active = isActive(path, n.href);
            return (
              <Link
                key={n.href}
                href={n.href}
                className={`whitespace-nowrap rounded-md px-3 py-1.5 text-sm transition-colors ${
                  active ? "bg-steel/10 font-medium text-steel" : "text-ink-2 hover:bg-paper hover:text-ink"
                }`}
              >
                {n.label}
              </Link>
            );
          })}
        </nav>

        <div className="ml-auto flex flex-wrap items-center gap-x-4 gap-y-1 text-sm">
          <span className="flex items-center gap-1.5 text-ink-2" title={error ?? undefined}>
            <span className={`h-2 w-2 rounded-full ${badge.dot}`} aria-hidden="true" />
            {badge.text}
          </span>
          {summary?.ai_mode === "amd" && !error && !stale && (
            <Link
              href="/amd/"
              className="rounded bg-steel/10 px-2 py-0.5 text-xs font-medium text-steel hover:bg-steel/15"
              title="Classification and alert explanations run on AMD Token Factory"
            >
              AI: AMD
            </Link>
          )}
          <button
            type="button"
            onClick={() => setPrefs({ sound: !sound })}
            aria-pressed={sound}
            title={sound ? "Alert sound on" : "Alert sound off"}
            className={`rounded-md p-1.5 ${sound ? "bg-steel/10 text-steel" : "text-ink-3 hover:text-ink"}`}
          >
            <BellIcon on={sound} />
            <span className="sr-only">{sound ? "Turn alert sound off" : "Turn alert sound on"}</span>
          </button>
          <span className="tabular-nums text-ink" suppressHydrationWarning>
            {now} <span className="text-ink-3">WIB</span>
          </span>
        </div>
      </div>
    </header>
  );
}

function BellIcon({ on }: { on: boolean }) {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M6 16V11a6 6 0 1 1 12 0v5l1.5 2h-15L6 16Z" />
      <path d="M10 20.5a2 2 0 0 0 4 0" />
      {!on && <path d="M4 4l16 16" />}
    </svg>
  );
}
