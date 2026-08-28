"""
Tool handlers for the FleetPilot agent.
The model never touches the database or external APIs directly — only through these
typed handlers, which validate every argument and return plain-dict results.
"""
from datetime import date
from typing import Optional
from sqlalchemy.orm import Session
from app.database.models import (
    Vehicle, MaintenanceRecord, MaintenanceTask, PartsRequest,
    VehicleStatus, IncidentSeverity, TaskStatus, PartsRequestStatus,
    NotificationChannel, NotificationStatus,
)
from app.integrations.nhtsa import decode_vin_sync, get_recalls_sync
from app.core.logging import get_logger
import uuid

logger = get_logger(__name__)


def _to_int(value, default: int) -> int:
    """LLM arguments arrive as int, float (Gemini) or string — coerce defensively."""
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


# --- read tools ----------------------------------------------------------------

def tool_get_vehicle(fleet_number: str, db: Session) -> dict:
    vehicle = db.query(Vehicle).filter(Vehicle.fleet_number == fleet_number).first()
    if not vehicle:
        return {"found": False, "error": f"Vehicle '{fleet_number}' not found in fleet database."}
    return {
        "found": True,
        "vehicle_id": str(vehicle.id),
        "fleet_number": vehicle.fleet_number,
        "vin": vehicle.vin,
        "make": vehicle.make,
        "model": vehicle.model,
        "year": vehicle.year,
        "mileage": vehicle.mileage,
        "status": vehicle.status.value,
        "fuel_type": vehicle.fuel_type,
        "last_service_date": vehicle.last_service_date.isoformat() if vehicle.last_service_date else None,
        "next_service_mileage": vehicle.next_service_mileage,
        "km_until_service": (vehicle.next_service_mileage - vehicle.mileage) if vehicle.next_service_mileage else None,
    }


def tool_get_maintenance_history(vehicle_id: str, db: Session) -> dict:
    try:
        uid = uuid.UUID(vehicle_id)
    except ValueError:
        return {"error": "Invalid vehicle_id format."}
    records = (
        db.query(MaintenanceRecord)
        .filter_by(vehicle_id=uid)
        .order_by(MaintenanceRecord.performed_at.desc())
        .limit(10)
        .all()
    )
    return {
        "vehicle_id": vehicle_id,
        "record_count": len(records),
        "records": [
            {
                "maintenance_type": r.maintenance_type,
                "description": r.description,
                "mileage": r.mileage,
                "performed_at": r.performed_at.isoformat() if r.performed_at else None,
            }
            for r in records
        ],
    }


def tool_decode_vin(vin: str, db: Session) -> dict:
    """NHTSA vPIC lookup. Also backfills fuel_type on the fleet record when it is missing."""
    result = decode_vin_sync(vin)
    if result.get("make") and db is not None:
        vehicle = db.query(Vehicle).filter(Vehicle.vin == result["vin"]).first()
        if vehicle and not vehicle.fuel_type and result.get("fuel_type"):
            vehicle.fuel_type = result["fuel_type"][:20]
            db.flush()
    return result


def tool_check_recalls(make: str, model: str, year) -> dict:
    return get_recalls_sync(make, model, _to_int(year, 0))


# --- write tools ---------------------------------------------------------------

def tool_create_maintenance_task(
    vehicle_id: str,
    incident_id: Optional[str],
    title: str,
    description: str,
    severity: str,
    db: Session,
) -> dict:
    # Validate vehicle exists
    try:
        v_uid = uuid.UUID(vehicle_id)
    except ValueError:
        return {"success": False, "error": "Invalid vehicle_id."}
    vehicle = db.query(Vehicle).filter(Vehicle.id == v_uid).first()
    if not vehicle:
        return {"success": False, "error": f"Vehicle {vehicle_id} not found."}

    # Validate severity
    try:
        sev = IncidentSeverity(severity.upper())
    except (ValueError, AttributeError):
        return {"success": False, "error": f"Invalid severity '{severity}'."}

    # Business rule: CRITICAL/HIGH requires human approval
    status = TaskStatus.PENDING_APPROVAL if sev in [IncidentSeverity.CRITICAL, IncidentSeverity.HIGH] else TaskStatus.APPROVED

    inc_uid = None
    if incident_id:
        try:
            inc_uid = uuid.UUID(incident_id)
        except ValueError:
            pass

    task = MaintenanceTask(
        vehicle_id=v_uid,
        incident_id=inc_uid,
        title=title[:200],
        description=description,
        severity=sev,
        status=status,
        ai_generated=True,
        due_date=date.today(),
    )
    db.add(task)
    db.flush()

    return {
        "success": True,
        "task_id": str(task.id),
        "title": title,
        "severity": sev.value,
        "status": status.value,
        "requires_approval": status == TaskStatus.PENDING_APPROVAL,
    }


def tool_update_vehicle_status(vehicle_id: str, new_status: str, db: Session) -> dict:
    try:
        uid = uuid.UUID(vehicle_id)
    except ValueError:
        return {"success": False, "error": "Invalid vehicle_id."}
    vehicle = db.query(Vehicle).filter(Vehicle.id == uid).first()
    if not vehicle:
        return {"success": False, "error": f"Vehicle {vehicle_id} not found."}

    try:
        status = VehicleStatus(new_status.upper())
    except (ValueError, AttributeError):
        return {"success": False, "error": f"Invalid status '{new_status}'."}

    old_status = vehicle.status.value
    vehicle.status = status
    db.flush()

    return {
        "success": True,
        "vehicle_id": vehicle_id,
        "fleet_number": vehicle.fleet_number,
        "old_status": old_status,
        "new_status": status.value,
    }


def tool_create_parts_request(
    task_id: str,
    parts: list[dict],
    db: Session,
) -> dict:
    try:
        t_uid = uuid.UUID(task_id)
    except ValueError:
        return {"success": False, "error": "Invalid task_id."}
    task = db.query(MaintenanceTask).filter(MaintenanceTask.id == t_uid).first()
    if not task:
        return {"success": False, "error": f"Task {task_id} not found."}

    created = []
    for part in parts or []:
        if isinstance(part, str):
            part = {"name": part}
        name = str(part.get("name", "")).strip()
        qty = max(1, _to_int(part.get("quantity", 1), 1))
        if not name:
            continue
        priority = "HIGH" if task.severity in [IncidentSeverity.CRITICAL, IncidentSeverity.HIGH] else "NORMAL"
        pr = PartsRequest(
            maintenance_task_id=t_uid,
            part_name=name[:200],
            quantity=qty,
            priority=priority,
            status=PartsRequestStatus.REQUESTED,
        )
        db.add(pr)
        created.append({"part_name": name, "quantity": qty})

    db.flush()
    return {"success": True, "task_id": task_id, "parts_created": created, "count": len(created)}


def tool_send_notification(
    recipient: str,
    subject: str,
    message: str,
    channel: str = "IN_APP",
    related_entity_type: Optional[str] = None,
    related_entity_id: Optional[str] = None,
    db: Session = None,
) -> dict:
    from app.integrations.notification import NotificationService
    svc = NotificationService(db)
    try:
        ch = NotificationChannel((channel or "IN_APP").upper())
    except ValueError:
        ch = NotificationChannel.IN_APP

    notification = svc.send(
        recipient=recipient,
        channel=ch,
        subject=subject,
        message=message,
        related_entity_type=related_entity_type,
        related_entity_id=related_entity_id,
    )
    return {
        "success": notification.status in [NotificationStatus.SENT, NotificationStatus.SIMULATED],
        "notification_id": str(notification.id),
        "channel": ch.value,
        "recipient": notification.recipient,
        "status": notification.status.value,
    }
