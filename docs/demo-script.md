# FleetPilot AI — Demo Script

## Setup Checklist

- [ ] PostgreSQL running (`docker compose up postgres -d`)
- [ ] Backend running (`uvicorn app.main:app --reload`)
- [ ] Database seeded (`python -m app.database.seed`)
- [ ] Frontend running (`npm run dev`)
- [ ] `.env` configured (Gemini key optional)
- [ ] Open http://localhost:5173

---

## Scene 1 — Dashboard Overview

Open the **Dashboard**.

> "FleetPilot monitors a fleet of 25 commercial vehicles in real-time."

Point out:
- Fleet KPIs (total, healthy, maintenance due, out of service)
- Fleet Risk Score — calculated deterministically from fleet state
- **ET-042** appears in Critical Alerts (pre-seeded CRITICAL brake incident)
- Upcoming maintenance: ET-019 (300 km), ET-027 (overdue), ET-031
- Recent agent activity (if any)

---

## Scene 2 — Critical Incident Analysis

Navigate to **AI Operations**.

> "A mechanic reports a brake issue with vehicle ET-042."

1. Click **"Demo: Critical Brake Issue"** to fill in the form.
2. Click **"Analyze with FleetPilot"**.

Watch the agent activity timeline:
```
✓ Received maintenance report
✓ GET_VEHICLE — Retrieved vehicle ET-042
✓ GET_MAINTENANCE_HISTORY — 4 records found
✓ Analyzed brake-system symptoms
✓ Classification: CRITICAL / BRAKE_SYSTEM
✓ CREATE_MAINTENANCE_TASK — MR-1042 created
✓ UPDATE_VEHICLE_STATUS — OUT_OF_SERVICE
✓ CREATE_PARTS_REQUEST — Brake pads, brake fluid
✓ SEND_NOTIFICATION — Fleet Manager notified
```

Point out the AI analysis panel:
- Category: BRAKE_SYSTEM
- Severity: CRITICAL
- Vehicle Status: OUT_OF_SERVICE
- Possible causes & recommended actions
- Required parts identified

> "Every action corresponds to a real tool call. The AI never directly touched the database."

---

## Scene 3 — Human Approval Workflow

Navigate to **Maintenance**.

> "CRITICAL tasks require human approval before proceeding."

1. Find **"MR-1042: Critical Brake System Inspection"** in Pending Approval.
2. Review the AI recommendation.
3. Click **Approve**.

Show the task moving to APPROVED status. Show that a notification was sent.

Navigate to **Vehicles → ET-042**.

> "The vehicle status has been updated to OUT OF SERVICE."

---

## Scene 4 — Proactive Fleet Health Scan

Navigate back to **AI Operations**.

Click **"Run AI Fleet Health Scan"**.

Show results:
- Vehicles scanned
- Overdue maintenance identified (ET-027)
- Upcoming maintenance identified (ET-019, ET-031)
- Tasks automatically created
- Notifications generated

Navigate to **Notifications** to show the generated notifications.

---

## Scene 5 — Vehicle Details

Navigate to **Vehicles → ET-027**.

> "ET-027 has overdue brake inspection — flagged in both maintenance history and current status."

Show:
- Maintenance history timeline
- Current status: MAINTENANCE_DUE
- Overdue by mileage

---

## Closing Statement

> "FleetPilot demonstrates three core capabilities:
> 
> 1. **Reactive AI** — understands unstructured reports, reasons about them, and executes a chain of tools to coordinate the response.
> 
> 2. **Human-in-the-loop** — CRITICAL actions always require manager approval before execution.
> 
> 3. **Proactive automation** — the fleet health scan identifies issues before they're reported, and can be scheduled via Cloud Scheduler.
>
> The AI does the coordination work. The manager retains the judgment."
