from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from datetime import date
import uuid

from app.api.dependencies import get_db
from app.database.models import (
    MaintenanceTask, TaskStatus, Vehicle, Incident, IncidentStatus,
    PartsRequest, Notification, NotificationChannel, NotificationStatus, AgentAction
)
from app.integrations.notification import NotificationService

router = APIRouter(prefix="/api/maintenance", tags=["maintenance"])


@router.get("")
def list_maintenance(db: Session = Depends(get_db)):
    tasks = (
        db.query(MaintenanceTask, Vehicle)
        .join(Vehicle, MaintenanceTask.vehicle_id == Vehicle.id)
        .order_by(MaintenanceTask.created_at.desc())
        .all()
    )
    return {"success": True, "data": [_task_with_vehicle(t, v, db) for t, v in tasks]}


@router.get("/tasks/{task_id}")
def get_task(task_id: str, db: Session = Depends(get_db)):
    task = _find_task(task_id, db)
    vehicle = db.query(Vehicle).filter(Vehicle.id == task.vehicle_id).first()
    parts = list(task.parts_requests.all())
    return {
        "success": True,
        "data": {
            **_task_detail(task),
            "vehicle": {"fleet_number": vehicle.fleet_number, "make": vehicle.make, "model": vehicle.model} if vehicle else None,
            "parts_requests": [_parts_request(p) for p in parts],
        },
    }


@router.post("/tasks/{task_id}/approve")
def approve_task(task_id: str, db: Session = Depends(get_db)):
    task = _find_task(task_id, db)
    if task.status != TaskStatus.PENDING_APPROVAL:
        raise HTTPException(status_code=400, detail={"code": "INVALID_STATE", "message": "Task is not pending approval."})

    task.status = TaskStatus.APPROVED

    # Update related incident
    if task.incident_id:
        incident = db.query(Incident).filter(Incident.id == task.incident_id).first()
        if incident and incident.status == IncidentStatus.AWAITING_APPROVAL:
            incident.status = IncidentStatus.APPROVED

    db.commit()
    db.refresh(task)

    # Send approval notification
    vehicle = db.query(Vehicle).filter(Vehicle.id == task.vehicle_id).first()
    svc = NotificationService(db)
    svc.notify_task_approved(task, vehicle)

    return {"success": True, "data": _task_detail(task)}


@router.post("/tasks/{task_id}/reject")
def reject_task(task_id: str, db: Session = Depends(get_db)):
    task = _find_task(task_id, db)
    if task.status != TaskStatus.PENDING_APPROVAL:
        raise HTTPException(status_code=400, detail={"code": "INVALID_STATE", "message": "Task is not pending approval."})

    task.status = TaskStatus.CANCELLED

    if task.incident_id:
        incident = db.query(Incident).filter(Incident.id == task.incident_id).first()
        if incident:
            incident.status = IncidentStatus.REJECTED

    db.commit()
    return {"success": True, "data": _task_detail(task)}


def _find_task(task_id: str, db: Session) -> MaintenanceTask:
    try:
        uid = uuid.UUID(task_id)
        task = db.query(MaintenanceTask).filter(MaintenanceTask.id == uid).first()
    except ValueError:
        task = None
    if not task:
        raise HTTPException(status_code=404, detail={"code": "TASK_NOT_FOUND", "message": f"Task '{task_id}' not found."})
    return task


def _task_detail(t: MaintenanceTask) -> dict:
    return {
        "id": str(t.id),
        "vehicle_id": str(t.vehicle_id),
        "incident_id": str(t.incident_id) if t.incident_id else None,
        "title": t.title,
        "description": t.description,
        "severity": t.severity,
        "status": t.status,
        "assigned_to": t.assigned_to,
        "due_date": t.due_date.isoformat() if t.due_date else None,
        "ai_generated": t.ai_generated,
        "created_at": t.created_at.isoformat() if t.created_at else None,
        "updated_at": t.updated_at.isoformat() if t.updated_at else None,
    }


def _task_with_vehicle(t: MaintenanceTask, v: Vehicle, db: Session) -> dict:
    parts_count = t.parts_requests.count()
    return {
        **_task_detail(t),
        "vehicle": {
            "fleet_number": v.fleet_number,
            "make": v.make,
            "model": v.model,
            "year": v.year,
        },
        "parts_count": parts_count,
    }


def _parts_request(p: PartsRequest) -> dict:
    return {
        "id": str(p.id),
        "part_name": p.part_name,
        "quantity": p.quantity,
        "priority": p.priority,
        "status": p.status,
    }
