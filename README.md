# FleetPilot AI

**AI-powered fleet maintenance coordination agent** — a production-quality MVP demonstrating reactive + proactive agentic automation for commercial vehicle fleet operations.

> FleetPilot doesn't replace the fleet manager's judgment. It eliminates the repetitive coordination work surrounding that judgment.

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│  React + TypeScript UI (Vite + Tailwind CSS)                │
│  Dashboard · Vehicles · Maintenance · AI Operations          │
└────────────────────────┬────────────────────────────────────┘
                         │ REST API
┌────────────────────────▼────────────────────────────────────┐
│  FastAPI (Python)                                            │
│  /api/dashboard  /api/vehicles  /api/incidents               │
│  /api/maintenance  /api/automation/fleet-health-scan         │
└───────────┬────────────────────────────┬────────────────────┘
            │                            │
┌───────────▼────────────┐  ┌───────────▼──────────────────┐
│  Agent Orchestrator     │  │  Deterministic Business Logic │
│  Gemini Tool Calling    │  │  Severity rules               │
│  Tool Registry          │  │  Approval gating              │
│  Action Logger          │  │  Status transitions           │
└───────────┬────────────┘  └──────────────────────────────┘
            │
┌───────────▼────────────────────────────────────────────────┐
│  PostgreSQL                                                  │
│  vehicles · incidents · maintenance_tasks · agent_actions    │
└────────────────────────────────────────────────────────────┘

External: NHTSA vPIC API · Resend Email · Google Cloud Scheduler
```

---

## Prerequisites

- Python 3.12+
- Node.js 20+
- Docker + Docker Compose (for PostgreSQL)
- Google Gemini API key (optional — demo mode available)

---

## Environment Setup

```bash
cp .env.example .env
```

Edit `.env`:

```env
DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:5432/fleetpilot

# Required for live AI — leave empty to run in demo mode
GEMINI_API_KEY=your_key_here
GEMINI_MODEL=gemini-1.5-flash

# Optional — leave empty to simulate emails
RESEND_API_KEY=
RESEND_FROM_EMAIL=fleet@yourdomain.com
```

---

## Local Setup

### 1. Start PostgreSQL

```bash
docker compose up postgres -d
```

### 2. Set up backend

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate   # Windows
source .venv/bin/activate  # macOS/Linux

pip install -r requirements.txt
```

### 3. Seed the database

```bash
cd backend
python -m app.database.seed
```

### 4. Start the backend

```bash
cd backend
uvicorn app.main:app --reload --port 8000
```

API docs: http://localhost:8000/docs

### 5. Start the frontend

```bash
cd frontend
npm install
npm run dev
```

App: http://localhost:5173

---

## Docker (Full Stack)

```bash
cp .env.example .env   # configure your keys
docker compose up --build
```

- Frontend: http://localhost:5173
- Backend API: http://localhost:8000
- API docs: http://localhost:8000/docs

---

## Running Tests

```bash
cd backend
pip install pytest pytest-asyncio
pytest tests/ -v
```

---

## Demo Walkthrough

See [docs/demo-script.md](docs/demo-script.md) for the full guided demo.

**Quick demo:**

1. Open http://localhost:5173
2. Navigate to **AI Operations**
3. Click **"Demo: Critical Brake Issue"**
4. Click **"Analyze with FleetPilot"**
5. Watch the agent activity timeline execute tools in real-time
6. Navigate to **Maintenance** and approve the generated task
7. Run **AI Fleet Health Scan** from the AI Operations screen

---

## External APIs

| Service | Purpose | Fallback |
|---------|---------|---------|
| Google Gemini | AI analysis + tool calling | Demo mode (keyword classification) |
| NHTSA vPIC | VIN decoding | Returns graceful error |
| Resend | Email notifications | Simulated (logged) |

---

## Known Limitations (MVP)

- No authentication — production deployment requires auth layer
- No real-time updates — polling required for live analysis progress
- Single-user demo scope
- No pagination on list endpoints
- Fleet health scan is synchronous (suitable for up to ~1,000 vehicles)

---

## Future Improvements

- WebSocket streaming for agent activity
- JWT authentication + RBAC
- Pagination and filtering
- Mileage tracking from telematics/GPS
- Historical trend analysis
- Predictive maintenance ML model
- Mobile app
- Full Cloud deployment with GCP Cloud Scheduler
