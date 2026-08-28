from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func
from pydantic import BaseModel
from typing import Optional
from datetime import date
import uuid

from app.api.dependencies import get_db
from app.database.models import (
    MaintenanceTask, TaskStatus, Vehicle, VehicleStatus, Incident, IncidentStatus,
    PartsRequest, PartsRequestStatus, MaintenanceRecord,
)
from app.integrations.notification import NotificationService

router = APIRouter(prefix="/api/maintenance", tags=["maintenance"])

SERVICE_INTERVAL_KM = 10_000


class CompleteTaskRequest(BaseModel):
    notes: Optional[str] = None
    mileage: Optional[int] = None


@router.get("")
def list_maintenance(db: Session = Depends(get_db)):
    tasks = (
        db.query(MaintenanceTask, Vehicle)
        .join(Vehicle, MaintenanceTask.vehicle_id == Vehicle.id)
        .order_by(MaintenanceTask.created_at.desc())
        .all()
    )
    return {"success": True, "data": [_task_with_vehicle(t, v) for t, v in tasks]}


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

    # Approved parts requests move to ORDERED
    for part in task.parts_requests.filter(PartsRequest.status == PartsRequestStatus.REQUESTED).all():
        part.status = PartsRequestStatus.ORDERED

    db.commit()
    db.refresh(task)

    vehicle = db.query(Vehicle).filter(Vehicle.id == task.vehicle_id).first()
    NotificationService(db).notify_task_approved(task, vehicle)
    db.commit()

    return {"success": True, "data": _task_with_vehicle(task, vehicle)}


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

    for part in task.parts_requests.filter(PartsRequest.status == PartsRequestStatus.REQUESTED).all():
        part.status = PartsRequestStatus.CANCELLED

    db.commit()
    db.refresh(task)
    vehicle = db.query(Vehicle).filter(Vehicle.id == task.vehicle_id).first()
    return {"success": True, "data": _task_with_vehicle(task, vehicle)}


@router.post("/tasks/{task_id}/start")
def start_task(task_id: str, db: Session = Depends(get_db)):
    task = _find_task(task_id, db)
    if task.status not in (TaskStatus.APPROVED, TaskStatus.ASSIGNED):
        raise HTTPException(status_code=400, detail={"code": "INVALID_STATE", "message": "Only approved tasks can be started."})

    task.status = TaskStatus.IN_PROGRESS
    if task.incident_id:
        incident = db.query(Incident).filter(Incident.id == task.incident_id).first()
        if incident and incident.status in (IncidentStatus.APPROVED, IncidentStatus.AWAITING_APPROVAL):
            incident.status = IncidentStatus.IN_PROGRESS
    db.commit()
    db.refresh(task)
    vehicle = db.query(Vehicle).filter(Vehicle.id == task.vehicle_id).first()
    return {"success": True, "data": _task_with_vehicle(task, vehicle)}


@router.post("/tasks/{task_id}/complete")
def complete_task(task_id: str, payload: Optional[CompleteTaskRequest] = None, db: Session = Depends(get_db)):
    """
    Close the loop: record the work, resolve the incident, reset the service interval
    for service tasks, and return the vehicle to ACTIVE once nothing else is open.
    """
    task = _find_task(task_id, db)
    if task.status not in (TaskStatus.APPROVED, TaskStatus.ASSIGNED, TaskStatus.IN_PROGRESS):
        raise HTTPException(status_code=400, detail={"code": "INVALID_STATE", "message": "Task must be approved or in progress to complete."})

    vehicle = db.query(Vehicle).filter(Vehicle.id == task.vehicle_id).first()
    notes = payload.notes if payload else None
    if payload and payload.mileage and vehicle and payload.mileage > vehicle.mileage:
        vehicle.mileage = payload.mileage

    task.status = TaskStatus.COMPLETED

    if vehicle:
        db.add(MaintenanceRecord(
            vehicle_id=vehicle.id,
            maintenance_type=task.title[:100],
            description=notes or task.description,
            mileage=vehicle.mileage,
            performed_at=date.today(),
            status="COMPLETED",
        ))
        if "service" in task.title.lower():
            vehicle.last_service_date = date.today()
            vehicle.next_service_mileage = vehicle.mileage + SERVICE_INTERVAL_KM

    for part in task.parts_requests.filter(PartsRequest.status.in_([PartsRequestStatus.REQUESTED, PartsRequestStatus.ORDERED])).all():
        part.status = PartsRequestStatus.RECEIVED

    if task.incident_id:
        incident = db.query(Incident).filter(Incident.id == task.incident_id).first()
        if incident and incident.status not in (IncidentStatus.REJECTED,):
            incident.status = IncidentStatus.RESOLVED

    db.flush()

    vehicle_restored = False
    if vehicle:
        open_tasks = db.query(func.count(MaintenanceTask.id)).filter(
            MaintenanceTask.vehicle_id == vehicle.id,
            MaintenanceTask.status.not_in([TaskStatus.COMPLETED, TaskStatus.CANCELLED]),
        ).scalar()
        open_incidents = db.query(func.count(Incident.id)).filter(
            Incident.vehicle_id == vehicle.id,
            Incident.status.not_in([IncidentStatus.RESOLVED, IncidentStatus.REJECTED]),
        ).scalar()
        if open_tasks == 0 and open_incidents == 0 and vehicle.status != VehicleStatus.ACTIVE:
            vehicle.status = VehicleStatus.ACTIVE
            vehicle_restored = True

    db.commit()
    db.refresh(task)
    NotificationService(db).notify_task_completed(task, vehicle, vehicle_restored)
    db.commit()

    return {
        "success": True,
        "data": {
            **_task_with_vehicle(task, vehicle),
            "vehicle_status": vehicle.status if vehicle else None,
            "vehicle_restored": vehicle_restored,
        },
    }


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


def _task_with_vehicle(t: MaintenanceTask, v: Optional[Vehicle]) -> dict:
    return {
        **_task_detail(t),
        "vehicle": {
            "fleet_number": v.fleet_number,
            "make": v.make,
            "model": v.model,
            "year": v.year,
        } if v else None,
        "parts_count": t.parts_requests.count(),
    }


def _parts_request(p: PartsRequest) -> dict:
    return {
        "id": str(p.id),
        "part_name": p.part_name,
        "quantity": p.quantity,
        "priority": p.priority,
        "status": p.status,
    }
