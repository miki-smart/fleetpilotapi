"""
Tool definitions for the FleetPilot agent.
Each function returns data that the agent can use for reasoning.
Gemini never accesses the database directly — only through these typed tool handlers.
"""
from datetime import datetime, date
from typing import Optional
from sqlalchemy.orm import Session
from app.database.models import (
    Vehicle, MaintenanceRecord, Incident, MaintenanceTask, PartsRequest,
    Notification, AgentAction,
    VehicleStatus, IncidentSeverity, TaskStatus, PartsRequestStatus,
    NotificationChannel, NotificationStatus, AgentActionType, AgentActionStatus,
)
from app.core.logging import get_logger
import uuid

logger = get_logger(__name__)


# --- Tool handler implementations ---

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
    except ValueError:
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
        title=title,
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
    except ValueError:
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
    for part in parts:
        name = part.get("name", "").strip()
        qty = int(part.get("quantity", 1))
        if not name:
            continue
        priority = "HIGH" if task.severity in [IncidentSeverity.CRITICAL, IncidentSeverity.HIGH] else "NORMAL"
        pr = PartsRequest(
            maintenance_task_id=t_uid,
            part_name=name,
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
        ch = NotificationChannel(channel.upper())
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
        "status": notification.status.value,
    }


def tool_record_agent_action(
    incident_id: Optional[str],
    action_type: str,
    description: str,
    tool_name: str,
    tool_input: Optional[dict],
    tool_output: Optional[dict],
    status: str = "SUCCESS",
    db: Session = None,
) -> dict:
    try:
        act_type = AgentActionType(action_type)
    except ValueError:
        act_type = AgentActionType.ANALYZE_INCIDENT

    act_status = AgentActionStatus.SUCCESS if status == "SUCCESS" else AgentActionStatus.FAILED

    inc_uid = None
    if incident_id:
        try:
            inc_uid = uuid.UUID(incident_id)
        except ValueError:
            pass

    action = AgentAction(
        incident_id=inc_uid,
        action_type=act_type,
        description=description,
        status=act_status,
        tool_name=tool_name,
        tool_input=tool_input,
        tool_output=tool_output,
        completed_at=datetime.utcnow(),
    )
    db.add(action)
    db.flush()
    return {"success": True, "action_id": str(action.id)}


def tool_get_fleet_health(db: Session) -> dict:
    from sqlalchemy import func
    from app.database.models import IncidentStatus
    total = db.query(func.count(Vehicle.id)).scalar()
    active = db.query(func.count(Vehicle.id)).filter(Vehicle.status == VehicleStatus.ACTIVE).scalar()
    maint_due = db.query(func.count(Vehicle.id)).filter(Vehicle.status == VehicleStatus.MAINTENANCE_DUE).scalar()
    oos = db.query(func.count(Vehicle.id)).filter(Vehicle.status == VehicleStatus.OUT_OF_SERVICE).scalar()
    unresolved_critical = db.query(func.count(Incident.id)).filter(
        Incident.severity == IncidentSeverity.CRITICAL,
        Incident.status.not_in([IncidentStatus.RESOLVED, IncidentStatus.REJECTED]),
    ).scalar()
    return {
        "total_vehicles": total,
        "active": active,
        "maintenance_due": maint_due,
        "out_of_service": oos,
        "unresolved_critical_incidents": unresolved_critical,
    }


def tool_get_upcoming_maintenance(db: Session) -> dict:
    vehicles = (
        db.query(Vehicle)
        .filter(
            Vehicle.next_service_mileage.isnot(None),
            Vehicle.status != VehicleStatus.OUT_OF_SERVICE,
        )
        .all()
    )
    overdue = []
    upcoming = []
    for v in vehicles:
        km_left = v.next_service_mileage - v.mileage
        entry = {
            "fleet_number": v.fleet_number,
            "make": v.make,
            "model": v.model,
            "current_mileage": v.mileage,
            "next_service_mileage": v.next_service_mileage,
            "km_until_service": km_left,
            "vehicle_id": str(v.id),
        }
        if km_left <= 0:
            overdue.append(entry)
        elif km_left <= 5000:
            upcoming.append(entry)

    return {
        "overdue": sorted(overdue, key=lambda x: x["km_until_service"]),
        "upcoming_within_5000km": sorted(upcoming, key=lambda x: x["km_until_service"]),
    }
