"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import { USING_SIMULATOR } from "@/lib/api";
import { nowWib } from "@/lib/format";
import { usePlant } from "@/lib/plant";

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

  return (
    <header className="mb-5 border-b border-rule bg-panel">
      <div className="mx-auto flex max-w-[1280px] flex-wrap items-center gap-x-8 gap-y-2 px-4 py-3 sm:px-6">
        <Link href="/" className="flex items-center gap-2.5">
          <Logo />
          <span className="text-[17px] font-semibold tracking-tight">SiagaMesin</span>
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

        <div className="ml-auto flex items-center gap-4 text-sm">
          <span className="flex items-center gap-1.5 text-ink-2" title={error ?? undefined}>
            <span className={`h-2 w-2 rounded-full ${badge.dot}`} aria-hidden="true" />
            {badge.text}
          </span>
          <span className="tabular-nums text-ink" suppressHydrationWarning>
            {now} <span className="text-ink-3">WIB</span>
          </span>
        </div>
      </div>
    </header>
  );
}

function Logo() {
  // A gauge needle in a square: "keeping watch over the machine".
  return (
    <svg width="26" height="26" viewBox="0 0 26 26" aria-hidden="true">
      <rect x="1" y="1" width="24" height="24" rx="5" fill="var(--color-ink)" />
      <path d="M6 17a7 7 0 0 1 14 0" fill="none" stroke="#fff" strokeWidth="2" strokeLinecap="round" />
      <path d="M13 17l4-5" stroke="var(--color-warn)" strokeWidth="2.2" strokeLinecap="round" />
      <circle cx="13" cy="17" r="1.6" fill="#fff" />
    </svg>
  );
}
