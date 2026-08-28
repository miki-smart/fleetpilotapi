# FleetPilot AI — API Reference

Base URL: `http://localhost:8000` · Interactive docs: `/docs`

All responses follow `{ "success": bool, "data": any }` or `{ "success": false, "error": { "code": str, "message": str } }`.

---

## Dashboard

### GET /api/dashboard
Fleet KPIs, risk score, pending approvals, critical alerts, upcoming maintenance, recent agent actions, and `automation` (last scan, next scheduled run).

---

## Vehicles

### GET /api/vehicles
Query params: `status` (ACTIVE | MAINTENANCE_DUE | OUT_OF_SERVICE)

### GET /api/vehicles/{vehicle_id}
Accepts UUID or fleet_number (e.g. `ET-042`). Returns vehicle + maintenance history + incidents.

### GET /api/vehicles/{vehicle_id}/maintenance

### POST /api/vehicles/decode-vin
Body: `{ "vin": "1FTFW1ET3DFC12345", "force": false }` — local record unless `force`, otherwise NHTSA vPIC.

---

## Incidents

### GET /api/incidents
### POST /api/incidents
Body: `{ "fleet_number": "ET-042", "reported_by": "Mechanic", "description": "..." }`

### GET /api/incidents/{incident_id}
Incident with vehicle, `agent_actions` (committed as they happen — poll this during analysis for a live timeline) and `maintenance_tasks`.

### POST /api/incidents/{incident_id}/analyze
Runs the FleetPilot agent (Gemini tool-calling loop). Returns
`{ incident_id, analysis, agent_actions, status, provider, demo_mode, demo_reason? }`.
On a provider failure after tools ran, returns `success: false` with `ANALYSIS_FAILED` and resets the incident to NEW.

---

## Maintenance

### GET /api/maintenance
### GET /api/maintenance/tasks/{task_id}
### POST /api/maintenance/tasks/{task_id}/approve — PENDING_APPROVAL → APPROVED; incident → APPROVED; parts → ORDERED; workshop notified
### POST /api/maintenance/tasks/{task_id}/reject — PENDING_APPROVAL → CANCELLED; incident → REJECTED
### POST /api/maintenance/tasks/{task_id}/start — APPROVED/ASSIGNED → IN_PROGRESS; incident → IN_PROGRESS
### POST /api/maintenance/tasks/{task_id}/complete
Body (optional): `{ "notes": "...", "mileage": 165200 }`. APPROVED/ASSIGNED/IN_PROGRESS → COMPLETED; writes a maintenance record; incident → RESOLVED; service tasks reset `next_service_mileage`; vehicle → ACTIVE when nothing else is open (`vehicle_restored: true`).

---

## Notifications

### GET /api/notifications — most recent 50 (channel, status SENT | SIMULATED | FAILED)
### GET /api/notifications/agent-actions — most recent 50 agent actions

---

## Automation

### POST /api/automation/fleet-health-scan
Proactive scan: service intervals (overdue / ≤ 2,000 km), NHTSA open recalls per make/model/year, reminders for approvals past the SLA, LLM-written digest emailed to the manager.

- Manual (UI): no header → recorded as `manual`.
- External scheduler: header `X-Scheduler-Token: <SCHEDULER_TOKEN>` and optional `?source=<label>` → recorded as `scheduler:<label>`; wrong token → 401.

Returns `{ scanned_at, triggered_by, vehicles_scanned, overdue_found, upcoming_found, recalls_found, tasks_created, notifications_sent, reminders_sent, findings[], digest, digest_provider, digest_email_status }`.

### GET /api/automation/status
`{ scheduler: { enabled, running, timezone, cron, interval_minutes, external_token_configured, jobs[] }, last_scan }`

---

## Settings

### GET /api/settings/ai — active provider, models, masked key hints
### POST /api/settings/ai — `{ provider?, gemini_model?, gemini_api_key?, groq_model?, groq_api_key? }` (applied immediately)
### GET /api/settings/ai/models?provider=gemini|groq — models available for the configured key

---

## Health

### GET /health → `{ "status": "ok", "service": "FleetPilot AI", "version": "1.1.0" }`
