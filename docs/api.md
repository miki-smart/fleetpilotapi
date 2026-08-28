# FleetPilot AI — API Reference

Base URL: `http://localhost:8000`

All responses follow: `{ "success": bool, "data": any }` or `{ "success": false, "error": { "code": str, "message": str } }`

---

## Dashboard

### GET /api/dashboard
Returns fleet KPIs, risk score, critical alerts, upcoming maintenance, and recent agent actions.

---

## Vehicles

### GET /api/vehicles
Query params: `status` (ACTIVE | MAINTENANCE_DUE | OUT_OF_SERVICE)

### GET /api/vehicles/{vehicle_id}
Accepts UUID or fleet_number (e.g. `ET-042`). Returns vehicle + maintenance history + incidents.

### GET /api/vehicles/{vehicle_id}/maintenance
Returns maintenance history for a vehicle.

### POST /api/vehicles/decode-vin
Body: `{ "vin": "JTFSX22P006123456" }`
Returns decoded vehicle information from NHTSA vPIC API.

---

## Incidents

### GET /api/incidents
List all incidents with vehicle info.

### POST /api/incidents
Body: `{ "fleet_number": "ET-042", "reported_by": "Mechanic", "description": "..." }`

### GET /api/incidents/{incident_id}
Returns incident with vehicle, agent_actions, and maintenance_tasks.

### POST /api/incidents/{incident_id}/analyze
Triggers the FleetPilot AI agent to analyze the incident.
This is the core agentic workflow endpoint.
Returns analysis result with agent action log.

---

## Maintenance

### GET /api/maintenance
List all maintenance tasks with vehicle info.

### GET /api/maintenance/tasks/{task_id}
Returns task detail with parts requests.

### POST /api/maintenance/tasks/{task_id}/approve
Approve a PENDING_APPROVAL task. Triggers notifications.

### POST /api/maintenance/tasks/{task_id}/reject
Reject a PENDING_APPROVAL task.

---

## Notifications

### GET /api/notifications
List notifications (most recent first, limit 50).

### GET /api/notifications/agent-actions
List recent agent actions.

---

## Automation

### POST /api/automation/fleet-health-scan
Runs a proactive fleet health scan:
- Identifies overdue maintenance (past next_service_mileage)
- Identifies upcoming maintenance (within 2,000 km)
- Creates maintenance tasks
- Generates notifications
- Records automation action

Designed to be called by Google Cloud Scheduler.

Returns: `{ scanned_at, vehicles_scanned, overdue_found, upcoming_found, tasks_created, notifications_sent, findings }`

---

## Health

### GET /health
Returns `{ "status": "ok", "service": "FleetPilot AI" }`
