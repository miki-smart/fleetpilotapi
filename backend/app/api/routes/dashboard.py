from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func
from datetime import date
from app.api.dependencies import get_db
from app.database.models import (
    Vehicle, VehicleStatus, Incident, IncidentSeverity, IncidentStatus,
    MaintenanceTask, TaskStatus, AgentAction
)

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


@router.get("")
def get_dashboard(db: Session = Depends(get_db)):
    total_vehicles = db.query(func.count(Vehicle.id)).scalar()
    healthy = db.query(func.count(Vehicle.id)).filter(Vehicle.status == VehicleStatus.ACTIVE).scalar()
    maintenance_due = db.query(func.count(Vehicle.id)).filter(Vehicle.status == VehicleStatus.MAINTENANCE_DUE).scalar()
    out_of_service = db.query(func.count(Vehicle.id)).filter(Vehicle.status == VehicleStatus.OUT_OF_SERVICE).scalar()

    # Risk score: weighted formula based on fleet state
    risk_score = _calculate_risk_score(total_vehicles, maintenance_due, out_of_service, db)

    # Critical alerts (CRITICAL incidents not yet resolved)
    critical_alerts = (
        db.query(Incident, Vehicle)
        .join(Vehicle, Incident.vehicle_id == Vehicle.id)
        .filter(
            Incident.severity == IncidentSeverity.CRITICAL,
            Incident.status.not_in([IncidentStatus.RESOLVED, IncidentStatus.REJECTED]),
        )
        .order_by(Incident.created_at.desc())
        .limit(10)
        .all()
    )

    # Upcoming maintenance (vehicles where next_service_mileage - mileage <= 5000)
    upcoming = (
        db.query(Vehicle)
        .filter(
            Vehicle.next_service_mileage.isnot(None),
            Vehicle.status != VehicleStatus.OUT_OF_SERVICE,
            (Vehicle.next_service_mileage - Vehicle.mileage) <= 5000,
            (Vehicle.next_service_mileage - Vehicle.mileage) > 0,
        )
        .order_by((Vehicle.next_service_mileage - Vehicle.mileage).asc())
        .limit(10)
        .all()
    )

    # Recent agent actions
    recent_actions = (
        db.query(AgentAction)
        .order_by(AgentAction.created_at.desc())
        .limit(15)
        .all()
    )

    # Pending approvals count
    pending_approvals = db.query(func.count(MaintenanceTask.id)).filter(
        MaintenanceTask.status == TaskStatus.PENDING_APPROVAL
    ).scalar()

    return {
        "success": True,
        "data": {
            "fleet_stats": {
                "total": total_vehicles,
                "healthy": healthy,
                "maintenance_due": maintenance_due,
                "out_of_service": out_of_service,
                "pending_approvals": pending_approvals,
            },
            "risk_score": risk_score,
            "critical_alerts": [
                {
                    "incident_id": str(i.id),
                    "vehicle_fleet_number": v.fleet_number,
                    "vehicle_make": v.make,
                    "vehicle_model": v.model,
                    "description": i.description[:120],
                    "severity": i.severity,
                    "status": i.status,
                    "category": i.category,
                    "created_at": i.created_at.isoformat() if i.created_at else None,
                }
                for i, v in critical_alerts
            ],
            "upcoming_maintenance": [
                {
                    "vehicle_id": str(v.id),
                    "fleet_number": v.fleet_number,
                    "make": v.make,
                    "model": v.model,
                    "km_until_service": v.next_service_mileage - v.mileage,
                    "next_service_mileage": v.next_service_mileage,
                    "current_mileage": v.mileage,
                    "status": v.status,
                }
                for v in upcoming
            ],
            "recent_agent_actions": [
                {
                    "id": str(a.id),
                    "action_type": a.action_type,
                    "description": a.description,
                    "status": a.status,
                    "tool_name": a.tool_name,
                    "created_at": a.created_at.isoformat() if a.created_at else None,
                    "incident_id": str(a.incident_id) if a.incident_id else None,
                }
                for a in recent_actions
            ],
        },
    }


def _calculate_risk_score(total: int, maintenance_due: int, out_of_service: int, db: Session) -> int:
    if total == 0:
        return 0
    unresolved_critical = db.query(func.count(Incident.id)).filter(
        Incident.severity == IncidentSeverity.CRITICAL,
        Incident.status.not_in([IncidentStatus.RESOLVED, IncidentStatus.REJECTED]),
    ).scalar()
    unresolved_high = db.query(func.count(Incident.id)).filter(
        Incident.severity == IncidentSeverity.HIGH,
        Incident.status.not_in([IncidentStatus.RESOLVED, IncidentStatus.REJECTED]),
    ).scalar()

    # Higher score = higher risk
    raw = (
        (out_of_service / total) * 50
        + (maintenance_due / total) * 25
        + min(unresolved_critical * 10, 20)
        + min(unresolved_high * 5, 10)
    )
    return min(int(raw), 100)
