"use client";

// Polls the live picture of the line once for the whole app, at the rates
// suggested in docs/role4-frontend.md, so every page shows the same data.

import { createContext, useContext, type ReactNode } from "react";
import { api } from "./api";
import type { AiUsage, Alert, Machine, StopEvent, Summary, TelemetryResponse } from "./types";
import { usePolling } from "./usePolling";

interface PlantData {
  machines: Machine[] | null;
  telemetry: TelemetryResponse | null;
  alerts: Alert[] | null; // active + raised today
  events: StopEvent[] | null; // today, newest first
  summary: Summary | null;
  /** Model behind /explain, e.g. "Qwen3.8-27B", once the backend has really used it. */
  explainModel: string | null;
  error: string | null;
  lastOk: number | null;
}

const PlantContext = createContext<PlantData | null>(null);

const fetchTelemetry = () => api.telemetry(2);
const fetchAlerts = () => api.alerts({ range: "today" });
const fetchEvents = () => api.events({ range: "today", limit: 50 });
const fetchSummary = () => api.summary("shift");

export function PlantProvider({ children }: { children: ReactNode }) {
  const machines = usePolling(api.machines, 1000);
  const telemetry = usePolling(fetchTelemetry, 2000);
  const alerts = usePolling(fetchAlerts, 2000);
  const events = usePolling(fetchEvents, 2000);
  const summary = usePolling(fetchSummary, 5000);
  const usage = usePolling(api.aiUsage, 30_000);

  return (
    <PlantContext.Provider
      value={{
        machines: machines.data,
        telemetry: telemetry.data,
        alerts: alerts.data,
        events: events.data,
        summary: summary.data,
        explainModel: explainModel(usage.data),
        error: machines.error,
        lastOk: machines.lastOk,
      }}
    >
      {children}
    </PlantContext.Provider>
  );
}

export function usePlant() {
  const ctx = useContext(PlantContext);
  if (!ctx) throw new Error("usePlant must be used inside <PlantProvider>");
  return ctx;
}

function explainModel(u: AiUsage | null) {
  const row = u?.endpoints.find((e) => e.endpoint === "/explain");
  return row && row.mock === false && row.model ? row.model : null;
}
