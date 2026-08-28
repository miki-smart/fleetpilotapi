"""
Proactive fleet health scan — the agent's daily check-in.

Triggered by the in-process scheduler, by an external scheduler (Cloud Scheduler /
GitHub Actions → POST /api/automation/fleet-health-scan), or manually from the UI.

Deterministic checks find the facts (mileage intervals, NHTSA open recalls, approvals
waiting past the SLA); the LLM turns them into a prioritized digest that is emailed
to the fleet manager. Everything the scan does is recorded as tasks, notifications
and an audit action.
"""
import asyncio
import json
import time
from datetime import datetime, date, timedelta
from typing import Optional
from sqlalchemy.orm import Session

from app.database.models import (
    Vehicle, MaintenanceTask, Incident, AgentAction, Notification,
    VehicleStatus, IncidentSeverity, IncidentStatus, TaskStatus,
    AgentActionType, AgentActionStatus, NotificationChannel,
)
from app.integrations.nhtsa import get_recalls_sync
from app.integrations.notification import NotificationService
from app.integrations.llm import generate_text, provider_label
from app.agents.prompts import FLEET_HEALTH_SCAN_PROMPT
from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)

UPCOMING_THRESHOLD_KM = 2000
_RECALL_CACHE_TTL_S = 24 * 3600
_RECALL_CONCURRENCY = 4
_REMINDER_COOLDOWN = timedelta(minutes=60)
_SAFETY_CRITICAL_COMPONENTS = ("BRAKE", "STEERING", "FUEL", "AIR BAG", "AIRBAG", "FIRE", "WHEEL", "SUSPENSION", "SEAT BELT")

# (make, model, year) -> (fetched_at, result). NHTSA data changes rarely; one lookup per day is plenty.
_recall_cache: dict[tuple, tuple[float, dict]] = {}


async def run_fleet_health_scan(db: Session, triggered_by: str = "manual") -> dict:
    settings = get_settings()
    started = time.monotonic()
    logger.info("fleet_health_scan_started", triggered_by=triggered_by)

    results = {
        "scanned_at": datetime.utcnow().isoformat(),
        "triggered_by": triggered_by,
        "vehicles_scanned": 0,
        "overdue_found": 0,
        "upcoming_found": 0,
        "recalls_found": 0,
        "tasks_created": 0,
        "notifications_sent": 0,
        "reminders_sent": 0,
        "findings": [],
        "digest": None,
        "digest_provider": None,
        "digest_email_status": None,
    }

    vehicles = (
        db.query(Vehicle)
        .filter(Vehicle.status != VehicleStatus.OUT_OF_SERVICE)
        .order_by(Vehicle.fleet_number)
        .all()
    )
    results["vehicles_scanned"] = len(vehicles)
    svc = NotificationService(db)

    # 1. Mileage-based service intervals
    for vehicle in vehicles:
        for finding in _check_service_interval(vehicle, db, svc):
            _record(results, finding)

    # 2. Open NHTSA recall campaigns (one lookup per make/model/year, cached for a day)
    recall_map = await _lookup_recalls(vehicles)
    for vehicle in vehicles:
        finding = _check_recalls(vehicle, recall_map.get(_recall_key(vehicle)), db, svc)
        if finding:
            _record(results, finding)

    # 3. Approvals waiting longer than the SLA
    results["reminders_sent"] = _remind_stale_approvals(db, svc, settings.approval_reminder_hours)
    if results["reminders_sent"]:
        results["notifications_sent"] += 2
    db.flush()

    # 4. AI digest for the fleet manager
    digest, provider = await _build_digest(results, db)
    results["digest"] = digest
    results["digest_provider"] = provider_label(provider) if provider else "Rule-based (LLM unavailable)"
    subject = (
        f"FleetPilot daily digest — {results['overdue_found']} overdue · "
        f"{results['recalls_found']} recall{'s' if results['recalls_found'] != 1 else ''} · "
        f"{results['upcoming_found']} upcoming"
    )
    sent = svc.send_digest(subject, digest)
    results["notifications_sent"] += len(sent)
    results["digest_email_status"] = next((n.status.value for n in sent if n.channel == NotificationChannel.EMAIL), None)

    # 5. Audit record
    duration = round(time.monotonic() - started, 1)
    action = AgentAction(
        incident_id=None,
        action_type=AgentActionType.FLEET_HEALTH_SCAN,
        description=(
            f"Fleet health scan ({triggered_by}): {results['vehicles_scanned']} vehicles checked — "
            f"{results['overdue_found']} overdue, {results['upcoming_found']} upcoming, "
            f"{results['recalls_found']} with open recalls, {results['tasks_created']} tasks created"
        ),
        status=AgentActionStatus.SUCCESS,
        tool_name="fleet_health_scan",
        tool_input={"triggered_by": triggered_by},
        tool_output={
            "overdue": results["overdue_found"],
            "upcoming": results["upcoming_found"],
            "recalls": results["recalls_found"],
            "tasks_created": results["tasks_created"],
            "notifications_sent": results["notifications_sent"],
            "reminders_sent": results["reminders_sent"],
            "digest_provider": results["digest_provider"],
            "digest_email_status": results["digest_email_status"],
            "duration_s": duration,
        },
        completed_at=datetime.utcnow(),
    )
    db.add(action)
    db.commit()

    logger.info("fleet_health_scan_completed", **{k: v for k, v in results.items() if k not in ("findings", "digest")})
    return results


# --- helpers -------------------------------------------------------------------------

def _record(results: dict, finding: dict) -> None:
    results["findings"].append(finding)
    key = {"OVERDUE": "overdue_found", "UPCOMING": "upcoming_found", "RECALL": "recalls_found"}.get(finding["type"])
    if key:
        results[key] += 1
    if finding.get("task_created"):
        results["tasks_created"] += 1
    if finding.get("notification_sent"):
        results["notifications_sent"] += 1


def _open_task_exists(vehicle: Vehicle, title_like: str, db: Session) -> bool:
    return (
        db.query(MaintenanceTask)
        .filter(
            MaintenanceTask.vehicle_id == vehicle.id,
            MaintenanceTask.status.not_in([TaskStatus.COMPLETED, TaskStatus.CANCELLED]),
            MaintenanceTask.title.like(title_like),
        )
        .first()
        is not None
    )


def _check_service_interval(vehicle: Vehicle, db: Session, svc: NotificationService) -> list[dict]:
    if not vehicle.next_service_mileage:
        return []

    km_remaining = vehicle.next_service_mileage - vehicle.mileage
    base = {
        "fleet_number": vehicle.fleet_number,
        "make": vehicle.make,
        "model": vehicle.model,
        "current_mileage": vehicle.mileage,
        "next_service_mileage": vehicle.next_service_mileage,
        "task_created": False,
        "notification_sent": False,
    }

    if km_remaining <= 0:
        finding = {**base, "type": "OVERDUE", "km_overdue": abs(km_remaining)}
        if not _open_task_exists(vehicle, "%Overdue Service%", db):
            db.add(MaintenanceTask(
                vehicle_id=vehicle.id,
                title=f"Overdue Service — {vehicle.fleet_number}",
                description=f"Maintenance overdue by {abs(km_remaining):,} km. Last service: {vehicle.last_service_date}.",
                severity=IncidentSeverity.HIGH,
                status=TaskStatus.PENDING_APPROVAL,
                ai_generated=True,
                due_date=date.today(),
            ))
            db.flush()
            finding["task_created"] = True
            if vehicle.status == VehicleStatus.ACTIVE:
                vehicle.status = VehicleStatus.MAINTENANCE_DUE
            svc.send(
                "Fleet Manager", NotificationChannel.IN_APP,
                f"[OVERDUE] {vehicle.fleet_number} — service overdue by {abs(km_remaining):,} km",
                f"Vehicle {vehicle.fleet_number} ({vehicle.make} {vehicle.model}) has exceeded its next service mileage by {abs(km_remaining):,} km. A HIGH-priority task is waiting for your approval.",
                "vehicle", str(vehicle.id),
            )
            finding["notification_sent"] = True
        return [finding]

    if km_remaining <= UPCOMING_THRESHOLD_KM:
        finding = {**base, "type": "UPCOMING", "km_remaining": km_remaining}
        if not _open_task_exists(vehicle, "%Upcoming Service%", db):
            db.add(MaintenanceTask(
                vehicle_id=vehicle.id,
                title=f"Upcoming Service — {vehicle.fleet_number}",
                description=f"Service due in {km_remaining:,} km. Schedule before the vehicle reaches {vehicle.next_service_mileage:,} km.",
                severity=IncidentSeverity.MEDIUM,
                status=TaskStatus.APPROVED,
                ai_generated=True,
            ))
            db.flush()
            finding["task_created"] = True
        return [finding]

    return []


def _recall_key(vehicle: Vehicle) -> tuple:
    return (vehicle.make.strip().lower(), vehicle.model.strip().lower(), int(vehicle.year))


async def _lookup_recalls(vehicles: list[Vehicle]) -> dict[tuple, dict]:
    now = time.monotonic()
    keys = {_recall_key(v): v for v in vehicles}
    fresh = {k: r for k, (t, r) in _recall_cache.items() if k in keys and now - t < _RECALL_CACHE_TTL_S}
    missing = [k for k in keys if k not in fresh]

    sem = asyncio.Semaphore(_RECALL_CONCURRENCY)

    async def fetch(key: tuple):
        v = keys[key]
        async with sem:
            return key, await asyncio.to_thread(get_recalls_sync, v.make, v.model, v.year)

    for key, result in await asyncio.gather(*(fetch(k) for k in missing)):
        # Cache successes, and 400s too — NHTSA answers 400 for models it does not
        # know (non-US market), which will not change between daily scans.
        if not result.get("error") or "400" in str(result.get("error")):
            _recall_cache[key] = (now, result)
        fresh[key] = result
    return fresh


def _check_recalls(vehicle: Vehicle, recall_result: Optional[dict], db: Session, svc: NotificationService) -> Optional[dict]:
    if not recall_result or recall_result.get("recall_count", 0) == 0:
        return None

    recalls = recall_result.get("recalls", [])
    components = " ".join((r.get("component") or "").upper() for r in recalls)
    safety_critical = any(marker in components for marker in _SAFETY_CRITICAL_COMPONENTS)
    severity = IncidentSeverity.HIGH if safety_critical else IncidentSeverity.MEDIUM
    top = recalls[0]

    finding = {
        "type": "RECALL",
        "fleet_number": vehicle.fleet_number,
        "make": vehicle.make,
        "model": vehicle.model,
        "current_mileage": vehicle.mileage,
        "recall_count": recall_result["recall_count"],
        "campaign_number": top.get("campaign_number"),
        "component": top.get("component"),
        "summary": top.get("summary"),
        "remedy": top.get("remedy"),
        "severity": severity.value,
        "task_created": False,
        "notification_sent": False,
    }

    if not _open_task_exists(vehicle, "%Safety Recall%", db):
        lines = [f"{r.get('campaign_number')}: {r.get('component')} — {r.get('summary')}" for r in recalls[:5]]
        db.add(MaintenanceTask(
            vehicle_id=vehicle.id,
            title=f"Open Safety Recall — {vehicle.fleet_number}: {(top.get('component') or 'campaign')[:80]}",
            description=(
                f"NHTSA lists {recall_result['recall_count']} open recall campaign(s) for the {vehicle.year} {vehicle.make} {vehicle.model}. "
                f"Verify applicability by VIN with the dealer; manufacturer remedy is typically free.\n\n" + "\n".join(lines)
            ),
            severity=severity,
            status=TaskStatus.PENDING_APPROVAL if severity == IncidentSeverity.HIGH else TaskStatus.APPROVED,
            ai_generated=True,
            due_date=date.today() + timedelta(days=7),
        ))
        db.flush()
        finding["task_created"] = True
        if severity == IncidentSeverity.HIGH:
            svc.send(
                "Fleet Manager", NotificationChannel.IN_APP,
                f"[RECALL] {vehicle.fleet_number} — open {top.get('component') or 'safety'} recall ({top.get('campaign_number')})",
                f"NHTSA campaign {top.get('campaign_number')} affects the {vehicle.year} {vehicle.make} {vehicle.model}. {top.get('consequence') or ''}".strip(),
                "vehicle", str(vehicle.id),
            )
            finding["notification_sent"] = True

    return finding


def _remind_stale_approvals(db: Session, svc: NotificationService, waiting_hours: int) -> int:
    cutoff = datetime.utcnow() - timedelta(hours=max(0, waiting_hours))
    stale = (
        db.query(MaintenanceTask, Vehicle)
        .outerjoin(Vehicle, MaintenanceTask.vehicle_id == Vehicle.id)
        .filter(MaintenanceTask.status == TaskStatus.PENDING_APPROVAL, MaintenanceTask.created_at <= cutoff)
        .order_by(MaintenanceTask.created_at.asc())
        .all()
    )
    if not stale:
        return 0

    # Don't nag more than once per cooldown window.
    recent = (
        db.query(Notification)
        .filter(
            Notification.related_entity_type == "approval_reminder",
            Notification.created_at >= datetime.utcnow() - _REMINDER_COOLDOWN,
        )
        .first()
    )
    if recent:
        return 0

    svc.send_approval_reminder(stale, waiting_hours)
    return len(stale)


async def _build_digest(results: dict, db: Session) -> tuple[str, Optional[str]]:
    open_incidents = (
        db.query(Incident, Vehicle)
        .join(Vehicle, Incident.vehicle_id == Vehicle.id)
        .filter(
            Incident.severity.in_([IncidentSeverity.CRITICAL, IncidentSeverity.HIGH]),
            Incident.status.not_in([IncidentStatus.RESOLVED, IncidentStatus.REJECTED]),
        )
        .order_by(Incident.created_at.desc())
        .limit(10)
        .all()
    )
    pending = (
        db.query(MaintenanceTask, Vehicle)
        .outerjoin(Vehicle, MaintenanceTask.vehicle_id == Vehicle.id)
        .filter(MaintenanceTask.status == TaskStatus.PENDING_APPROVAL)
        .order_by(MaintenanceTask.created_at.asc())
        .limit(15)
        .all()
    )

    context = {
        "scan_date": date.today().isoformat(),
        "vehicles_scanned": results["vehicles_scanned"],
        "overdue": [{k: f[k] for k in ("fleet_number", "make", "model", "km_overdue", "current_mileage")} for f in results["findings"] if f["type"] == "OVERDUE"],
        "upcoming": [{k: f[k] for k in ("fleet_number", "make", "model", "km_remaining")} for f in results["findings"] if f["type"] == "UPCOMING"],
        "recalls": [{k: f.get(k) for k in ("fleet_number", "make", "model", "recall_count", "campaign_number", "component", "remedy", "severity")} for f in results["findings"] if f["type"] == "RECALL"],
        "open_critical_high_incidents": [
            {"fleet_number": v.fleet_number, "severity": i.severity.value if i.severity else None, "category": i.category, "status": i.status.value, "reported": i.description[:140]}
            for i, v in open_incidents
        ],
        "awaiting_approval": [
            {"fleet_number": v.fleet_number if v else None, "title": t.title, "severity": t.severity.value, "waiting_since": t.created_at.isoformat() if t.created_at else None}
            for t, v in pending
        ],
    }

    text, provider = await generate_text(FLEET_HEALTH_SCAN_PROMPT, json.dumps(context, default=str), max_tokens=900)
    if text and text.strip():
        return text.strip(), provider
    return _deterministic_digest(context), None


def _deterministic_digest(ctx: dict) -> str:
    lines = [f"Fleet health scan — {ctx['scan_date']} — {ctx['vehicles_scanned']} vehicles checked", ""]
    lines.append("TOP PRIORITIES")
    priorities = [f"  {o['fleet_number']} ({o['make']} {o['model']}): service overdue by {o['km_overdue']:,} km" for o in ctx["overdue"]]
    priorities += [f"  {i['fleet_number']}: unresolved {i['severity']} {i['category'] or 'incident'} ({i['status']})" for i in ctx["open_critical_high_incidents"]]
    lines += priorities[:5] or ["  none"]
    lines += ["", "RECALLS"]
    lines += [f"  {r['fleet_number']} ({r['make']} {r['model']}): {r['recall_count']} open campaign(s), e.g. {r['campaign_number']} — {r['component']}" for r in ctx["recalls"]] or ["  none"]
    lines += ["", "UPCOMING"]
    lines += [f"  {u['fleet_number']} ({u['make']} {u['model']}): service due in {u['km_remaining']:,} km" for u in ctx["upcoming"]] or ["  none"]
    lines += ["", "AWAITING YOUR APPROVAL"]
    lines += [f"  {a['fleet_number']}: {a['title']} ({a['severity']})" for a in ctx["awaiting_approval"]] or ["  none"]
    return "\n".join(lines)
