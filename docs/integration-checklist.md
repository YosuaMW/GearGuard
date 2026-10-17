# Integration Checklist Between Roles

What needs to be agreed so the backend (role 2) can connect to roles 1, 3 and 4. Format details are in each role's document. Just reply **"ok"** if a proposal works, or suggest a change.

| Topic | Role | Priority | Status |
|---|---|---|---|
| `/transcribe` + `/classify` | 3 | 🔴 Required | ✅ Live: Whisper on the Pi + Qwen3.8-27B on AMD Token Factory |
| `/explain` | 3 | 🟡 Important | ✅ Live: cites PDF manuals (per-machine `MANUAL_MAP`) and repair history |
| Dashboard API | 4 | 🟡 Important | ✅ Done, live at https://gearguard-sky.vercel.app |
| `/score` | 1 | 🟢 Optional | Backend uses z-score fallback |
| Extra vibration features | 1 | 🟢 Optional | Not needed unless the model asks |

---

## 🔴 1. `/transcribe` + `/classify` · role 3

Operator voice note → text → downtime category. Details: [role3-ai.md](role3-ai.md).

- [ ] **Endpoint URL** on AMD + **API key** (send by DM, never in the group or repo)
- [ ] **Audio upload:** the Telegram `.ogg` file as-is, `multipart/form-data` field `file`. Or does role 3 need another format (`.wav`, base64)?
- [ ] **`/transcribe` response:** `{"text": "..."}`
- [ ] **`/classify` response:** `{"category": "...", "confidence": 0.86}`
- [ ] **The 7 category names exactly as listed**, including the `–` (en dash). The backend maps them to the English labels the dashboard shows
- [ ] **"Needs review" threshold:** confidence < 0.6?
- [ ] **Processing time:** < 10 s total

**If not agreed:** the bot keeps classifying with keyword rules, so the flow works, but the demo can't claim the AI runs on AMD.

## 🟡 2. `/explain` · role 3

Anomaly alert → LLM explanation + sources from the manual.

- [ ] **Data the backend sends:** machine, score, each sensor now vs normal, recent breakdowns. Enough, or is more needed?
- [ ] **Response:** `summary`, `actions`, `urgency`, `sources` (manual title + page)
- [ ] **Language:** English, matching the Telegram bot and dashboard
- [ ] **Manuals for RAG** (sourced by role 5)
- [ ] **Processing time:** < 15 s
- [ ] **`usage` field** (model, latency, tokens) in every response, for the "Running on AMD" page

**If not agreed:** alerts still go out with a rule-based explanation, but the MVP requirement *"alerts explained by an LLM with manual sources"* isn't met.

## 🟡 3. Dashboard · role 4

Details: [role4-frontend.md](role4-frontend.md).

- [x] Endpoints for every dashboard page (`/summary`, `/telemetry`, `/events`, `/alerts`, `/pareto`, `/availability`, `/ai-usage`)
- [x] Machine names and English category labels match the dashboard
- [x] **Vercel URL** added to CORS (`gearguard-sky.vercel.app`)
- [ ] Any field missing or shaped differently than the dashboard expects

## 🟢 4. `/score` · role 1 · optional

Used if the autoencoder is ready. Details: [role1-hardware.md](role1-hardware.md#5-score-contract-autoencoder).

- [ ] **Where it runs:** AMD Cloud or the Raspberry Pi?
- [ ] **Input:** last 60 seconds (current, vibration, temperature)
- [ ] **Response:** `{"score": 0–1, "anomaly": true/false}`
- [ ] **Processing time:** < 1 s

**If not built:** the demo still works with the existing z-score detection; say so honestly in the pitch, as planned in the team's fallback.

## 🟢 5. Extra vibration features · role 1 · optional

- [ ] Is `vib_rms` enough, or does the model need more (`vib_peak`, FFT bands)?
- [ ] If so: the field names in the MQTT JSON, so database columns can be added

**If not discussed:** `vib_rms` only. Bearing-wear detection already works with it.

---

## Decisions log

| Topic | Decision | By | Date |
|---|---|---|---|
| STT | Token Factory has no working audio model → Whisper in the `stt` container on the Pi | Yosua | 15 Oct |
| AI service | Role 3's `AI/` service runs on the Pi as the `ai` container | Yosua + role 3 | 15 Oct |
| Dashboard domain | `gearguard-sky.vercel.app` | Yosua | 15 Oct |
