from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional
import uuid

from app.api.dependencies import get_db
from app.database.models import Vehicle, MaintenanceRecord, Incident, VehicleStatus
from app.core.exceptions import VehicleNotFoundError
from app.integrations.nhtsa import decode_vin_from_nhtsa

router = APIRouter(prefix="/api/vehicles", tags=["vehicles"])


class DecodeVINRequest(BaseModel):
    vin: str
    force: bool = False


@router.get("")
def list_vehicles(status: Optional[str] = None, db: Session = Depends(get_db)):
    q = db.query(Vehicle)
    if status:
        try:
            q = q.filter(Vehicle.status == VehicleStatus(status))
        except ValueError:
            pass
    vehicles = q.order_by(Vehicle.fleet_number).all()
    return {"success": True, "data": [_vehicle_summary(v) for v in vehicles]}


@router.get("/{vehicle_id}")
def get_vehicle(vehicle_id: str, db: Session = Depends(get_db)):
    vehicle = _find_vehicle(vehicle_id, db)
    records = (
        db.query(MaintenanceRecord)
        .filter_by(vehicle_id=vehicle.id)
        .order_by(MaintenanceRecord.performed_at.desc())
        .all()
    )
    incidents = (
        db.query(Incident)
        .filter_by(vehicle_id=vehicle.id)
        .order_by(Incident.created_at.desc())
        .limit(10)
        .all()
    )
    return {
        "success": True,
        "data": {
            **_vehicle_detail(vehicle),
            "maintenance_history": [_maintenance_record(r) for r in records],
            "incidents": [_incident_summary(i) for i in incidents],
        },
    }


@router.get("/{vehicle_id}/maintenance")
def get_vehicle_maintenance(vehicle_id: str, db: Session = Depends(get_db)):
    vehicle = _find_vehicle(vehicle_id, db)
    records = (
        db.query(MaintenanceRecord)
        .filter_by(vehicle_id=vehicle.id)
        .order_by(MaintenanceRecord.performed_at.desc())
        .all()
    )
    return {"success": True, "data": [_maintenance_record(r) for r in records]}


@router.post("/decode-vin")
async def decode_vin(request: DecodeVINRequest, db: Session = Depends(get_db)):
    vin = request.vin.strip().upper()
    if len(vin) != 17:
        return {"success": False, "error": {"code": "INVALID_VIN", "message": "VIN must be exactly 17 characters."}}

    # Unless forced, return the local record if we already have this VIN
    if not request.force:
        existing = db.query(Vehicle).filter(Vehicle.vin == vin).first()
        if existing:
            return {"success": True, "source": "database", "data": _vehicle_detail(existing)}

    result = await decode_vin_from_nhtsa(vin)
    return {"success": True, "source": "nhtsa", "data": result}


def _find_vehicle(vehicle_id: str, db: Session) -> Vehicle:
    # Accept both UUID and fleet_number
    try:
        uid = uuid.UUID(vehicle_id)
        vehicle = db.query(Vehicle).filter(Vehicle.id == uid).first()
    except ValueError:
        vehicle = db.query(Vehicle).filter(Vehicle.fleet_number == vehicle_id).first()
    if not vehicle:
        raise HTTPException(status_code=404, detail={"code": "VEHICLE_NOT_FOUND", "message": f"Vehicle '{vehicle_id}' not found."})
    return vehicle


def _vehicle_summary(v: Vehicle) -> dict:
    return {
        "id": str(v.id),
        "fleet_number": v.fleet_number,
        "make": v.make,
        "model": v.model,
        "year": v.year,
        "mileage": v.mileage,
        "status": v.status,
        "fuel_type": v.fuel_type,
        "last_service_date": v.last_service_date.isoformat() if v.last_service_date else None,
        "next_service_mileage": v.next_service_mileage,
        "km_until_service": (v.next_service_mileage - v.mileage) if v.next_service_mileage else None,
    }


def _vehicle_detail(v: Vehicle) -> dict:
    return {
        **_vehicle_summary(v),
        "vin": v.vin,
        "created_at": v.created_at.isoformat() if v.created_at else None,
        "updated_at": v.updated_at.isoformat() if v.updated_at else None,
    }


def _maintenance_record(r: MaintenanceRecord) -> dict:
    return {
        "id": str(r.id),
        "maintenance_type": r.maintenance_type,
        "description": r.description,
        "mileage": r.mileage,
        "performed_at": r.performed_at.isoformat() if r.performed_at else None,
        "status": r.status,
    }


def _incident_summary(i: Incident) -> dict:
    return {
        "id": str(i.id),
        "description": i.description[:100],
        "severity": i.severity,
        "category": i.category,
        "status": i.status,
        "created_at": i.created_at.isoformat() if i.created_at else None,
    }
