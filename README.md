# FleetPilot AI

**AI fleet maintenance coordinator** for commercial vehicle fleets — an agent that triages mechanics' reports, opens work orders, requests parts, grounds unsafe vehicles, checks NHTSA safety recalls, emails the manager, and runs a proactive fleet scan every morning on its own. Humans keep the approvals.

> The model recommends. Python enforces. The manager decides.

- 📄 **Solution design / SRS:** [docs/solution-design.md](docs/solution-design.md)
- 🏗️ Architecture: [docs/architecture.md](docs/architecture.md) · API: [docs/api.md](docs/api.md) · Deployment & scheduling: [docs/deployment.md](docs/deployment.md) · Demo script: [docs/demo-script.md](docs/demo-script.md)

---

## What it does

| Mode | Trigger | What the agent does |
|---|---|---|
| **Reactive** | Mechanic submits a free-text report | Reads the vehicle + history, checks open **NHTSA recalls**, classifies category/severity, creates a task, requests parts, escalates vehicle status, **emails the manager**, submits a structured verdict — every step a real, audited tool call streamed live to the UI |
| **Proactive** | Scheduler (06:00 daily, in-process APScheduler; also Cloud Scheduler / GitHub Actions via a signed endpoint) | Finds overdue/upcoming services and open recall campaigns, creates tasks, reminds the manager about approvals past the SLA, and emails a **Gemini-written daily digest** |
| **Human-in-the-loop** | Manager in the UI | Approve / reject CRITICAL & HIGH work; start / complete tasks → incident resolved, history logged, vehicle back in service |

Business rules live in Python, not the prompt: CRITICAL → `OUT_OF_SERVICE` + approval; HIGH → `MAINTENANCE_DUE` + approval; a task and a manager email always exist for CRITICAL/HIGH even if the model skipped a tool.

---

## Architecture

```
React + TypeScript (Vite, Tailwind)  ──REST + polling──▶  FastAPI
  Dashboard · Vehicles · Incidents · Maintenance             ├─ Agent orchestrator: Gemini tool loop → normalize → rules → enforce
  AI Operations (live timeline) · Notifications · Settings   ├─ Tool handlers (typed, validated, audited)
                                                             ├─ Proactive scan + APScheduler
                                                             └─ PostgreSQL 16
External (all free): Gemini API · NHTSA vPIC · NHTSA Recalls · Resend · Groq (optional) · Cloud Scheduler / GitHub Actions
```

---

## Quick start

Prerequisites: Python 3.12+, Node 20+, Docker (for Postgres).

```bash
cp .env.example .env         # add GEMINI_API_KEY (free at aistudio.google.com), RESEND_API_KEY, FLEET_MANAGER_EMAIL
docker compose up postgres -d

cd backend
python -m venv .venv && .venv\Scripts\activate      # macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
python -m app.database.seed --reset                 # 25 vehicles, history, one seeded CRITICAL incident
uvicorn app.main:app --reload --port 8000           # API docs: http://localhost:8000/docs

cd ../frontend
npm install && npm run dev                          # http://localhost:5173
```

Full stack in Docker: `docker compose up --build` (UI on :5173, API on :8000).

### Environment

| Variable | Notes |
|---|---|
| `GEMINI_API_KEY` / `GEMINI_MODEL` | Primary provider. Default model `gemini-3.6-flash`. Leave empty → clearly-labelled demo mode |
| `GROQ_API_KEY` / `GROQ_MODEL` | Optional alternative, switchable in **Settings** at runtime |
| `RESEND_API_KEY`, `RESEND_FROM_EMAIL`, `FLEET_MANAGER_EMAIL` | Email. Resend test mode only delivers to the account owner's address until a domain is verified; empty key → `SIMULATED` |
| `SCHEDULER_ENABLED`, `SCAN_SCHEDULE_CRON`, `SCHEDULER_TIMEZONE`, `SCAN_INTERVAL_MINUTES` | Proactive scan schedule (interval is handy for demos) |
| `SCHEDULER_TOKEN` | Shared secret external schedulers send as `X-Scheduler-Token` |
| `APPROVAL_REMINDER_HOURS` | Reminder SLA for pending approvals |

---

## Demo in 90 seconds

1. **AI Operations** → *Demo: Engine Overheating (Ford Transit)* → **Analyze** — watch tool calls stream in, including real NHTSA recall campaigns; check the manager's inbox.
2. **Maintenance** → Approve → Start → Complete — vehicle returns to ACTIVE, history logged.
3. **Run Fleet Health Scan** — overdue, upcoming, open recalls, tasks created, Gemini digest **emailed**; Dashboard shows last/next scheduled run.

---

## External APIs (all free, no card)

| Service | Used for | Fallback |
|---|---|---|
| Google Gemini (AI Studio) | Agent reasoning + tool calling, digest writing | Back-off on rate limits; demo mode if unreachable (labelled) |
| NHTSA vPIC | VIN → specs | Error object, analysis continues |
| NHTSA Recalls | Open campaigns per make/model/year (agent tool + daily scan) | Cached 24 h; skipped on error |
| Resend | Manager emails: alerts, reminders, digest | `SIMULATED` without a key |
| Groq | Optional LLM provider | — |

---

## Tests

```bash
cd backend && pip install -r tests/requirements-test.txt && pytest tests/ -v    # business rules, verdict parsing, tool handlers
cd frontend && npx tsc -b --noEmit                                               # type-check
```

Live checks performed during development: Gemini 3.6 Flash analysis end-to-end, NHTSA recalls returning real campaigns (Ford Transit/Ranger, Toyota Land Cruiser), Resend delivery, scheduler token guard (401 on bad token), APScheduler next-run reporting.

---

## Project layout

```
backend/app
  agents/         fleet_agent.py (tool schemas) · prompts.py · orchestrator.py · tools.py · schemas.py
  integrations/   gemini.py · groq_client.py · llm.py · nhtsa.py · notification.py
  automation/     fleet_health_scan.py · scheduler.py
  api/routes/     dashboard · vehicles · incidents · maintenance · notifications · automation · settings
  database/       models.py · session.py · seed.py (--reset)
frontend/src
  pages/          Dashboard · Vehicles · VehicleDetails · Incidents · Maintenance · AgentOperations · Notifications · Settings
  components/     layout (responsive sidebar) · ui
  services/api.ts · types/index.ts
docs/             solution-design.md · architecture.md · api.md · deployment.md · demo-script.md
.github/workflows/fleet-health-scan.yml   free external scheduler
```

## Known limitations (MVP)

No authentication (single-tenant demo; scheduler endpoint is token-protected), manual mileage (no telematics), NHTSA recall data covers US-market vehicles, list endpoints unpaginated.
