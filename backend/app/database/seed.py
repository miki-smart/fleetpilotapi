"""
Seed script — idempotent, safe to run multiple times.
Creates ~25 vehicles with maintenance records matching the three demo scenarios.
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from datetime import date, timedelta
from sqlalchemy.orm import Session
from app.database.session import SessionLocal, engine
from app.database.models import (
    Base, Vehicle, MaintenanceRecord, Incident, MaintenanceTask, AgentAction,
    VehicleStatus, IncidentSeverity, IncidentStatus, TaskStatus, AgentActionType, AgentActionStatus
)


VEHICLE_DATA = [
    # Demo vehicles
    {"fleet_number": "ET-042", "vin": "JTFSX22P006123456", "make": "Toyota", "model": "Hiace",
     "year": 2021, "mileage": 182400, "status": VehicleStatus.OUT_OF_SERVICE,
     "fuel_type": "Diesel", "last_service_date": date(2024, 3, 15), "next_service_mileage": 185000},

    {"fleet_number": "ET-019", "vin": "1FTFW1ET3DFC12345", "make": "Ford", "model": "Transit",
     "year": 2020, "mileage": 164700, "status": VehicleStatus.MAINTENANCE_DUE,
     "fuel_type": "Diesel", "last_service_date": date(2024, 2, 28), "next_service_mileage": 165000},

    {"fleet_number": "ET-027", "vin": "WDB9063331L234567", "make": "Mercedes", "model": "Sprinter",
     "year": 2019, "mileage": 211300, "status": VehicleStatus.MAINTENANCE_DUE,
     "fuel_type": "Diesel", "last_service_date": date(2023, 10, 10), "next_service_mileage": 200000},

    # Active fleet
    {"fleet_number": "ET-001", "vin": "1HGBH41JXMN109186", "make": "Toyota", "model": "Land Cruiser",
     "year": 2022, "mileage": 78200, "status": VehicleStatus.ACTIVE,
     "fuel_type": "Diesel", "last_service_date": date(2024, 6, 1), "next_service_mileage": 90000},

    {"fleet_number": "ET-003", "vin": "2T2BZMCA8KC187234", "make": "Toyota", "model": "Hilux",
     "year": 2021, "mileage": 112500, "status": VehicleStatus.ACTIVE,
     "fuel_type": "Diesel", "last_service_date": date(2024, 5, 20), "next_service_mileage": 125000},

    {"fleet_number": "ET-005", "vin": "3VWFE21C04M000001", "make": "Isuzu", "model": "NPR",
     "year": 2020, "mileage": 143800, "status": VehicleStatus.ACTIVE,
     "fuel_type": "Diesel", "last_service_date": date(2024, 4, 15), "next_service_mileage": 155000},

    {"fleet_number": "ET-008", "vin": "WBAFR9C55BC762810", "make": "Mitsubishi", "model": "Fuso",
     "year": 2022, "mileage": 91000, "status": VehicleStatus.ACTIVE,
     "fuel_type": "Diesel", "last_service_date": date(2024, 7, 1), "next_service_mileage": 100000},

    {"fleet_number": "ET-010", "vin": "JN1AZ4EH2FM730000", "make": "Nissan", "model": "Urvan",
     "year": 2021, "mileage": 98300, "status": VehicleStatus.ACTIVE,
     "fuel_type": "Petrol", "last_service_date": date(2024, 6, 10), "next_service_mileage": 110000},

    {"fleet_number": "ET-012", "vin": "5XYKT3A63FG500001", "make": "Toyota", "model": "Coaster",
     "year": 2020, "mileage": 156200, "status": VehicleStatus.ACTIVE,
     "fuel_type": "Diesel", "last_service_date": date(2024, 3, 25), "next_service_mileage": 168000},

    {"fleet_number": "ET-014", "vin": "1GYS3BEF6FR100001", "make": "Ford", "model": "Ranger",
     "year": 2023, "mileage": 42100, "status": VehicleStatus.ACTIVE,
     "fuel_type": "Diesel", "last_service_date": date(2024, 7, 15), "next_service_mileage": 55000},

    {"fleet_number": "ET-016", "vin": "4T1BF3EK6AU100001", "make": "Toyota", "model": "Hiace",
     "year": 2022, "mileage": 119600, "status": VehicleStatus.ACTIVE,
     "fuel_type": "Diesel", "last_service_date": date(2024, 5, 10), "next_service_mileage": 130000},

    {"fleet_number": "ET-018", "vin": "JN8AS5MT4AW100001", "make": "Hino", "model": "300",
     "year": 2021, "mileage": 138700, "status": VehicleStatus.ACTIVE,
     "fuel_type": "Diesel", "last_service_date": date(2024, 4, 8), "next_service_mileage": 150000},

    {"fleet_number": "ET-020", "vin": "2HNYD28607H100001", "make": "Mitsubishi", "model": "Canter",
     "year": 2020, "mileage": 171900, "status": VehicleStatus.ACTIVE,
     "fuel_type": "Diesel", "last_service_date": date(2024, 2, 14), "next_service_mileage": 185000},

    {"fleet_number": "ET-022", "vin": "1N4AL3AP6DC100001", "make": "Toyota", "model": "Land Cruiser",
     "year": 2019, "mileage": 224100, "status": VehicleStatus.ACTIVE,
     "fuel_type": "Diesel", "last_service_date": date(2024, 1, 20), "next_service_mileage": 235000},

    {"fleet_number": "ET-024", "vin": "1FTFW1RG0NFC00001", "make": "Ford", "model": "Transit",
     "year": 2023, "mileage": 38400, "status": VehicleStatus.ACTIVE,
     "fuel_type": "Diesel", "last_service_date": date(2024, 7, 20), "next_service_mileage": 50000},

    {"fleet_number": "ET-026", "vin": "3C6UR5DL0HG100001", "make": "Isuzu", "model": "D-Max",
     "year": 2022, "mileage": 87500, "status": VehicleStatus.ACTIVE,
     "fuel_type": "Diesel", "last_service_date": date(2024, 6, 5), "next_service_mileage": 100000},

    {"fleet_number": "ET-028", "vin": "1GTG6CEN0F1100001", "make": "Nissan", "model": "NP300",
     "year": 2021, "mileage": 104300, "status": VehicleStatus.ACTIVE,
     "fuel_type": "Diesel", "last_service_date": date(2024, 5, 28), "next_service_mileage": 115000},

    {"fleet_number": "ET-030", "vin": "4T1G11AKXMU100001", "make": "Toyota", "model": "Hilux",
     "year": 2022, "mileage": 69800, "status": VehicleStatus.ACTIVE,
     "fuel_type": "Diesel", "last_service_date": date(2024, 7, 1), "next_service_mileage": 80000},

    {"fleet_number": "ET-031", "vin": "1FMSK7DH4LGA00001", "make": "Mitsubishi", "model": "Fuso",
     "year": 2020, "mileage": 188600, "status": VehicleStatus.MAINTENANCE_DUE,
     "fuel_type": "Diesel", "last_service_date": date(2024, 1, 10), "next_service_mileage": 200000},

    {"fleet_number": "ET-033", "vin": "3GCPCREC0BG100001", "make": "Hino", "model": "500",
     "year": 2019, "mileage": 252100, "status": VehicleStatus.ACTIVE,
     "fuel_type": "Diesel", "last_service_date": date(2024, 2, 5), "next_service_mileage": 265000},

    {"fleet_number": "ET-035", "vin": "5TBBV54167S100001", "make": "Toyota", "model": "Coaster",
     "year": 2021, "mileage": 131200, "status": VehicleStatus.ACTIVE,
     "fuel_type": "Diesel", "last_service_date": date(2024, 4, 22), "next_service_mileage": 145000},

    {"fleet_number": "ET-037", "vin": "1C4RJFCG8FC100001", "make": "Isuzu", "model": "NPR",
     "year": 2022, "mileage": 76400, "status": VehicleStatus.ACTIVE,
     "fuel_type": "Diesel", "last_service_date": date(2024, 6, 18), "next_service_mileage": 90000},

    {"fleet_number": "ET-039", "vin": "1GCWGFCG4B1100001", "make": "Ford", "model": "Ranger",
     "year": 2020, "mileage": 158300, "status": VehicleStatus.ACTIVE,
     "fuel_type": "Diesel", "last_service_date": date(2024, 3, 12), "next_service_mileage": 170000},

    {"fleet_number": "ET-041", "vin": "2GNALBEK9F6100001", "make": "Mitsubishi", "model": "Canter",
     "year": 2021, "mileage": 118900, "status": VehicleStatus.ACTIVE,
     "fuel_type": "Diesel", "last_service_date": date(2024, 5, 5), "next_service_mileage": 130000},

    {"fleet_number": "ET-044", "vin": "1VWBP7A33CC100001", "make": "Nissan", "model": "Urvan",
     "year": 2023, "mileage": 28600, "status": VehicleStatus.ACTIVE,
     "fuel_type": "Petrol", "last_service_date": date(2024, 7, 25), "next_service_mileage": 40000},
]


MAINTENANCE_RECORDS = {
    "ET-042": [
        {"type": "Oil Change", "mileage": 172000, "date": date(2024, 3, 15), "desc": "Engine oil and filter replaced"},
        {"type": "Tire Rotation", "mileage": 165000, "date": date(2023, 12, 10), "desc": "All 4 tires rotated"},
        {"type": "General Service", "mileage": 155000, "date": date(2023, 9, 5), "desc": "Full service including brake inspection"},
        {"type": "Brake Inspection", "mileage": 140000, "date": date(2023, 5, 20), "desc": "Brake pads at 40% — monitor"},
    ],
    "ET-019": [
        {"type": "Oil Change", "mileage": 155000, "date": date(2024, 2, 28), "desc": "Engine oil changed, filter replaced"},
        {"type": "Filter Replacement", "mileage": 145000, "date": date(2023, 11, 14), "desc": "Air filter and fuel filter replaced"},
    ],
    "ET-027": [
        {"type": "Brake Inspection", "mileage": 195000, "date": date(2023, 10, 10), "desc": "Brake pads worn — flagged for replacement"},
        {"type": "General Service", "mileage": 180000, "date": date(2023, 6, 8), "desc": "Full service completed"},
        {"type": "Oil Change", "mileage": 170000, "date": date(2023, 3, 22), "desc": "Engine oil changed"},
    ],
}


def seed(db: Session) -> None:
    print("Starting database seed...")

    # Create vehicles (upsert by fleet_number)
    vehicle_map: dict[str, Vehicle] = {}
    for vd in VEHICLE_DATA:
        existing = db.query(Vehicle).filter_by(fleet_number=vd["fleet_number"]).first()
        if existing:
            vehicle_map[vd["fleet_number"]] = existing
            continue
        v = Vehicle(**vd)
        db.add(v)
        db.flush()
        vehicle_map[vd["fleet_number"]] = v
        print(f"  Created vehicle {vd['fleet_number']}")

    # Create maintenance records
    for fleet_num, records in MAINTENANCE_RECORDS.items():
        vehicle = vehicle_map.get(fleet_num)
        if not vehicle:
            continue
        existing_count = db.query(MaintenanceRecord).filter_by(vehicle_id=vehicle.id).count()
        if existing_count > 0:
            continue
        for r in records:
            mr = MaintenanceRecord(
                vehicle_id=vehicle.id,
                maintenance_type=r["type"],
                mileage=r["mileage"],
                performed_at=r["date"],
                description=r["desc"],
                status="COMPLETED",
            )
            db.add(mr)
        print(f"  Created maintenance records for {fleet_num}")

    # Scenario A: ET-042 has existing CRITICAL incident (pre-seeded for demo)
    et042 = vehicle_map.get("ET-042")
    if et042:
        existing_incident = db.query(Incident).filter_by(vehicle_id=et042.id).first()
        if not existing_incident:
            incident = Incident(
                vehicle_id=et042.id,
                reported_by="Mechanic - James Bekele",
                description="Vehicle ET-042 has a grinding noise when braking and the brake pedal feels softer than usual.",
                severity=IncidentSeverity.CRITICAL,
                category="BRAKE_SYSTEM",
                status=IncidentStatus.AWAITING_APPROVAL,
                ai_analysis={
                    "category": "BRAKE_SYSTEM",
                    "severity": "CRITICAL",
                    "vehicle_status": "OUT_OF_SERVICE",
                    "summary": "The reported symptoms — grinding noise during braking and soft pedal feel — indicate a potentially unsafe brake-system condition requiring immediate attention.",
                    "possible_causes": ["Worn brake pads", "Damaged brake rotor", "Hydraulic brake fluid leak"],
                    "recommended_actions": ["Stop vehicle operation immediately", "Inspect brake pads and rotors", "Check brake fluid level and lines", "Do not operate until repaired"],
                    "required_parts": [{"name": "Brake pads (front)", "quantity": 1}, {"name": "Brake pads (rear)", "quantity": 1}, {"name": "Brake fluid DOT 4", "quantity": 2}],
                    "requires_manager_approval": True,
                },
            )
            db.add(incident)
            db.flush()

            task = MaintenanceTask(
                vehicle_id=et042.id,
                incident_id=incident.id,
                title="MR-1042: Critical Brake System Inspection",
                description="Immediate brake system inspection required. Grinding noise and soft pedal indicate worn pads and possible hydraulic issue.",
                severity=IncidentSeverity.CRITICAL,
                status=TaskStatus.PENDING_APPROVAL,
                ai_generated=True,
                due_date=date.today(),
            )
            db.add(task)
            print("  Created Scenario A: Critical brake incident for ET-042")

    db.commit()
    print("Seed completed successfully.")


if __name__ == "__main__":
    print("Creating database tables...")
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        seed(db)
    finally:
        db.close()
