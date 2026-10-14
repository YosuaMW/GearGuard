# SiagaMesin Dashboard

Web dashboard for SiagaMesin (AMD Developer Hackathon ACT III, Intelligent Industry track).
Shows machine status, predictive alerts with explanations, operator downtime reasons from voice notes,
Availability and the downtime Pareto.

Stack: Next.js 16 (App Router, static export), Tailwind CSS 4, ECharts, IBM Plex Sans.

## Run

```bash
npm install
cp .env.example .env.local   # set NEXT_PUBLIC_API_URL, see below
npm run dev                  # http://localhost:3000
```

## Data source

| `NEXT_PUBLIC_API_URL` | What the dashboard shows | Badge in the header |
|---|---|---|
| `https://yosua.tailf140ab.ts.net` | Real backend on the Raspberry Pi. M1 is the live rig, M2–M4 come from the backend's replay simulator | "Live data · M1" or "Simulated data" |
| empty | Built-in browser simulator with the same response shapes. Backup for when the Pi is unreachable | "Demo data (offline)" |

The browser simulator repeats a scripted scenario every 2 minutes: M3 starts stopped and waits for the
operator, gets a voice-note reason at 40 s; M2 vibration creeps up from 45 s and raises an alert, stops at
80 s and is answered at 95 s.

`NEXT_PUBLIC_API_URL` is read at build time. After changing it on Vercel, redeploy.

## Backend contract

The API is owned by role 2: [docs/role4-frontend.md](https://github.com/YosuaMW/SiagaMesin/blob/main/docs/role4-frontend.md).
The same shapes are typed in [`src/lib/types.ts`](src/lib/types.ts). Times arrive in UTC and are shown in WIB.

| Dashboard part | Endpoint | Poll |
|---|---|---|
| Line diagram, machine cards, alert limit lines (`baseline.*.limit_high`) | `/machines` | 1 s |
| Vibration sparklines, machine charts | `/telemetry?minutes=2` | 2 s |
| Predictive alerts, "anomaly alert raised" rows | `/alerts?range=today` | 2 s |
| Today on the line, stops and operator answers | `/events?range=today` | 2 s |
| KPI row and data badge | `/summary?range=shift` | 5 s |
| Reports | `/pareto`, `/availability` (shift, today, 24 h) | 10 s |
| Running on AMD | `/ai-usage` | 10 s |

The backend must allow the dashboard's origin in `CORS_ORIGINS` (send the Vercel URL to role 2).

## Deploy (Vercel)

1. Import the repo on vercel.com. If the dashboard lives in a subfolder, set Root Directory to it.
2. Add `NEXT_PUBLIC_API_URL` under Environment Variables, then Deploy.
3. Optional backup: a second Vercel project from the same repo with `NEXT_PUBLIC_API_URL` empty.

`npm run build` writes plain HTML/CSS/JS to `out/`, so any static web server also works.

## Where things are

```
src/lib/api.ts        every backend call goes through here (add a login token here later)
src/lib/mock.ts       browser simulator, used when NEXT_PUBLIC_API_URL is empty
src/lib/plant.tsx     polls machines/telemetry/alerts/events/summary once for the whole app
src/app/page.tsx      Overview
src/app/machines/     Machine detail (ids listed in generateStaticParams)
src/app/reports/      Pareto and availability
src/app/amd/          Running on AMD
```

## Design rule

Grey when normal, colour only when abnormal (ISA-101 high-performance HMI). Amber = anomaly,
red = stopped, dashed grey = offline. Keep new UI to that rule so problems stay the first thing the eye finds.
