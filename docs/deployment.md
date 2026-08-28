# FleetPilot AI — Deployment & Scheduling

## 1. Local (recommended for the demo)

```bash
cp .env.example .env            # fill GEMINI_API_KEY, RESEND_API_KEY, FLEET_MANAGER_EMAIL
docker compose up postgres -d
cd backend && python -m venv .venv && .venv\Scripts\activate && pip install -r requirements.txt
python -m app.database.seed --reset      # clean demo database
uvicorn app.main:app --port 8000
cd ../frontend && npm install && npm run dev   # http://localhost:5173
```

The in-process scheduler starts with the API: daily at `SCAN_SCHEDULE_CRON` (default 06:00 Africa/Addis_Ababa) and, when `SCAN_INTERVAL_MINUTES > 0`, every N minutes. `GET /api/automation/status` shows the next run.

## 2. Docker Compose (full stack)

```bash
docker compose up --build
# frontend http://localhost:5173 · API http://localhost:8000 · docs http://localhost:8000/docs
```

## 3. External scheduler (proactive trigger from outside the process)

The scan endpoint accepts an external trigger authenticated with a shared secret:

```
POST /api/automation/fleet-health-scan?source=<label>
X-Scheduler-Token: <SCHEDULER_TOKEN>
```

Wrong or missing token with the header present → `401`. Runs are recorded as `scheduler:<label>` and shown on the dashboard.

### 3a. GitHub Actions (free, no card) — provided

`.github/workflows/fleet-health-scan.yml` runs daily at 03:00 UTC (06:00 Addis) and can be run manually. Set repository secrets:

- `FLEETPILOT_API_URL` — e.g. `https://fleetpilot-api.onrender.com`
- `FLEETPILOT_SCHEDULER_TOKEN` — same value as `SCHEDULER_TOKEN` on the server

### 3b. Google Cloud Scheduler (Always Free: 3 jobs/month)

> In practice Cloud Scheduler and Cloud Run require a billing account to be linked even for free-tier usage. If your project has one, the commands below work; otherwise use 3a.

```bash
gcloud services enable cloudscheduler.googleapis.com
gcloud scheduler jobs create http fleetpilot-daily-scan \
  --location=europe-west1 \
  --schedule="0 6 * * *" --time-zone="Africa/Addis_Ababa" \
  --uri="https://<your-api-host>/api/automation/fleet-health-scan?source=cloud-scheduler" \
  --http-method=POST \
  --headers="X-Scheduler-Token=<SCHEDULER_TOKEN>,Content-Type=application/json" \
  --message-body="{}"
```

## 4. Hosting the API and UI

### Option A — Cloud Run (GCP)

```bash
gcloud run deploy fleetpilot-api --source ./backend --region europe-west1 \
  --allow-unauthenticated --port 8000 \
  --set-env-vars "DATABASE_URL=<neon-url>,GEMINI_API_KEY=...,RESEND_API_KEY=...,FLEET_MANAGER_EMAIL=...,SCHEDULER_TOKEN=...,SCHEDULER_ENABLED=false,CORS_ORIGINS=https://<your-ui-host>"
```

Set `SCHEDULER_ENABLED=false` on scale-to-zero platforms and rely on the external trigger (a sleeping instance cannot run cron). Cloud SQL has no free tier — use **Neon** (free Postgres, no card) for `DATABASE_URL`.

### Option B — no-card stack

| Layer | Service | Notes |
|---|---|---|
| Postgres | Neon free tier | copy the `postgresql://` URL and prefix `postgresql+psycopg://` |
| API | Render free web service (Docker, `./backend`) | set env vars from `.env.example`; `SCHEDULER_ENABLED=false` |
| UI | Vercel / Netlify (`frontend`, build `npm run build`, dir `dist`) | set `VITE_API_URL=https://<api-host>` |
| Scheduler | GitHub Actions workflow (3a) | free |

## 5. Environment variables

| Variable | Purpose |
|---|---|
| `DATABASE_URL` | SQLAlchemy URL (`postgresql+psycopg://…`) |
| `GEMINI_API_KEY`, `GEMINI_MODEL` | Primary AI provider (Google AI Studio, free) — default model `gemini-3.6-flash` |
| `GROQ_API_KEY`, `GROQ_MODEL` | Optional alternative provider |
| `RESEND_API_KEY`, `RESEND_FROM_EMAIL` | Email delivery; empty key → simulated |
| `FLEET_MANAGER_EMAIL` | Where role "Fleet Manager" emails go (Resend test mode: the account owner's address) |
| `SCHEDULER_ENABLED`, `SCHEDULER_TIMEZONE`, `SCAN_SCHEDULE_CRON`, `SCAN_INTERVAL_MINUTES` | In-process scheduler |
| `SCHEDULER_TOKEN` | Shared secret for external schedulers |
| `APPROVAL_REMINDER_HOURS` | Reminder SLA for pending approvals |
| `NHTSA_BASE_URL`, `NHTSA_RECALLS_BASE_URL` | NHTSA endpoints (free, no key) |
| `CORS_ORIGINS` | Allowed UI origins |
