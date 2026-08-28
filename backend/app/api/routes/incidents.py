from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional
import uuid

from app.api.dependencies import get_db
from app.database.models import Incident, Vehicle, AgentAction, IncidentStatus
from app.agents.orchestrator import run_incident_analysis

router = APIRouter(prefix="/api/incidents", tags=["incidents"])


class CreateIncidentRequest(BaseModel):
    fleet_number: str
    reported_by: Optional[str] = "Mechanic"
    description: str


@router.get("")
def list_incidents(db: Session = Depends(get_db)):
    rows = (
        db.query(Incident, Vehicle)
        .join(Vehicle, Incident.vehicle_id == Vehicle.id)
        .order_by(Incident.created_at.desc())
        .all()
    )
    return {"success": True, "data": [_incident_with_vehicle(i, v) for i, v in rows]}


@router.post("")
def create_incident(request: CreateIncidentRequest, db: Session = Depends(get_db)):
    vehicle = db.query(Vehicle).filter(Vehicle.fleet_number == request.fleet_number).first()
    if not vehicle:
        raise HTTPException(status_code=404, detail={"code": "VEHICLE_NOT_FOUND", "message": f"Vehicle '{request.fleet_number}' not found."})

    incident = Incident(
        vehicle_id=vehicle.id,
        reported_by=request.reported_by,
        description=request.description,
        status=IncidentStatus.NEW,
    )
    db.add(incident)
    db.commit()
    db.refresh(incident)

    return {"success": True, "data": _incident_detail(incident)}


@router.get("/{incident_id}")
def get_incident(incident_id: str, db: Session = Depends(get_db)):
    incident = _find_incident(incident_id, db)
    vehicle = db.query(Vehicle).filter(Vehicle.id == incident.vehicle_id).first()
    actions = list(incident.agent_actions.order_by(AgentAction.created_at.asc()).all())
    tasks = list(incident.maintenance_tasks.all())

    return {
        "success": True,
        "data": {
            **_incident_detail(incident),
            "vehicle": {
                "fleet_number": vehicle.fleet_number,
                "make": vehicle.make,
                "model": vehicle.model,
                "year": vehicle.year,
                "mileage": vehicle.mileage,
                "status": vehicle.status,
            } if vehicle else None,
            "agent_actions": [_agent_action(a) for a in actions],
            "maintenance_tasks": [_task_summary(t) for t in tasks],
        },
    }


@router.post("/{incident_id}/analyze")
async def analyze_incident(incident_id: str, db: Session = Depends(get_db)):
    incident = _find_incident(incident_id, db)
    if incident.status not in [IncidentStatus.NEW, IncidentStatus.ANALYZING]:
        raise HTTPException(status_code=400, detail={"code": "INVALID_STATE", "message": f"Incident is already in state {incident.status}."})

    result = await run_incident_analysis(incident_id=str(incident.id), db=db)
    if result.get("error"):
        return {
            "success": False,
            "error": {"code": "ANALYSIS_FAILED", "message": result["error"]},
            "data": result,
        }
    return {"success": True, "data": result}


def _find_incident(incident_id: str, db: Session) -> Incident:
    try:
        uid = uuid.UUID(incident_id)
        incident = db.query(Incident).filter(Incident.id == uid).first()
    except ValueError:
        incident = None
    if not incident:
        raise HTTPException(status_code=404, detail={"code": "INCIDENT_NOT_FOUND", "message": f"Incident '{incident_id}' not found."})
    return incident


def _incident_detail(i: Incident) -> dict:
    return {
        "id": str(i.id),
        "vehicle_id": str(i.vehicle_id),
        "reported_by": i.reported_by,
        "description": i.description,
        "severity": i.severity,
        "category": i.category,
        "status": i.status,
        "ai_analysis": i.ai_analysis,
        "created_at": i.created_at.isoformat() if i.created_at else None,
        "updated_at": i.updated_at.isoformat() if i.updated_at else None,
    }


def _incident_with_vehicle(i: Incident, v: Vehicle) -> dict:
    return {
        **_incident_detail(i),
        "vehicle_fleet_number": v.fleet_number,
        "vehicle_make": v.make,
        "vehicle_model": v.model,
    }


def _agent_action(a: AgentAction) -> dict:
    return {
        "id": str(a.id),
        "action_type": a.action_type,
        "description": a.description,
        "status": a.status,
        "tool_name": a.tool_name,
        "tool_input": a.tool_input,
        "tool_output": a.tool_output,
        "created_at": a.created_at.isoformat() if a.created_at else None,
        "completed_at": a.completed_at.isoformat() if a.completed_at else None,
    }


def _task_summary(t) -> dict:
    return {
        "id": str(t.id),
        "title": t.title,
        "severity": t.severity,
        "status": t.status,
        "ai_generated": t.ai_generated,
    }
