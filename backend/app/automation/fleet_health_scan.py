"""
Proactive fleet health scan.
Callable via POST /api/automation/fleet-health-scan or Cloud Scheduler.
"""
from datetime import datetime, date
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.database.models import (
    Vehicle, MaintenanceTask, Incident, AgentAction, Notification,
    VehicleStatus, IncidentSeverity, IncidentStatus, TaskStatus,
    AgentActionType, AgentActionStatus, NotificationChannel, NotificationStatus,
)
from app.core.logging import get_logger

logger = get_logger(__name__)


async def run_fleet_health_scan(db: Session) -> dict:
    logger.info("fleet_health_scan_started")

    scan_results = {
        "scanned_at": datetime.utcnow().isoformat(),
        "vehicles_scanned": 0,
        "overdue_found": 0,
        "upcoming_found": 0,
        "tasks_created": 0,
        "notifications_sent": 0,
        "findings": [],
    }

    vehicles = db.query(Vehicle).filter(Vehicle.status != VehicleStatus.OUT_OF_SERVICE).all()
    scan_results["vehicles_scanned"] = len(vehicles)

    for vehicle in vehicles:
        findings = _check_vehicle(vehicle, db)
        for finding in findings:
            scan_results["findings"].append(finding)
            if finding["type"] == "OVERDUE":
                scan_results["overdue_found"] += 1
            elif finding["type"] == "UPCOMING":
                scan_results["upcoming_found"] += 1

            if finding.get("task_created"):
                scan_results["tasks_created"] += 1
            if finding.get("notification_sent"):
                scan_results["notifications_sent"] += 1

    # Record automation action
    action = AgentAction(
        incident_id=None,
        action_type=AgentActionType.FLEET_HEALTH_SCAN,
        description=f"Fleet health scan: {scan_results['vehicles_scanned']} vehicles checked, {scan_results['overdue_found']} overdue, {scan_results['upcoming_found']} upcoming",
        status=AgentActionStatus.SUCCESS,
        tool_name="fleet_health_scan",
        tool_input={"triggered_by": "api"},
        tool_output={
            "overdue": scan_results["overdue_found"],
            "upcoming": scan_results["upcoming_found"],
            "tasks_created": scan_results["tasks_created"],
        },
        completed_at=datetime.utcnow(),
    )
    db.add(action)
    db.commit()

    logger.info("fleet_health_scan_completed", **{k: v for k, v in scan_results.items() if k != "findings"})
    return scan_results


def _check_vehicle(vehicle: Vehicle, db: Session) -> list[dict]:
    findings = []

    if not vehicle.next_service_mileage:
        return findings

    km_remaining = vehicle.next_service_mileage - vehicle.mileage

    if km_remaining <= 0:
        # Overdue maintenance
        existing_task = (
            db.query(MaintenanceTask)
            .filter(
                MaintenanceTask.vehicle_id == vehicle.id,
                MaintenanceTask.status.not_in([TaskStatus.COMPLETED, TaskStatus.CANCELLED]),
                MaintenanceTask.title.like("%Overdue%"),
            )
            .first()
        )

        finding = {
            "type": "OVERDUE",
            "fleet_number": vehicle.fleet_number,
            "make": vehicle.make,
            "model": vehicle.model,
            "current_mileage": vehicle.mileage,
            "next_service_mileage": vehicle.next_service_mileage,
            "km_overdue": abs(km_remaining),
            "task_created": False,
            "notification_sent": False,
        }

        if not existing_task:
            task = MaintenanceTask(
                vehicle_id=vehicle.id,
                title=f"Overdue Service — {vehicle.fleet_number}",
                description=f"Maintenance overdue by {abs(km_remaining):,} km. Last service: {vehicle.last_service_date}.",
                severity=IncidentSeverity.HIGH,
                status=TaskStatus.PENDING_APPROVAL,
                ai_generated=True,
                due_date=date.today(),
            )
            db.add(task)
            db.flush()
            finding["task_created"] = True

            # Update vehicle status if still ACTIVE
            if vehicle.status == VehicleStatus.ACTIVE:
                vehicle.status = VehicleStatus.MAINTENANCE_DUE

            # Send notification
            notif = Notification(
                recipient="Fleet Manager",
                channel=NotificationChannel.IN_APP,
                subject=f"[OVERDUE] {vehicle.fleet_number} — Service overdue by {abs(km_remaining):,} km",
                message=f"Vehicle {vehicle.fleet_number} ({vehicle.make} {vehicle.model}) has exceeded its next service mileage by {abs(km_remaining):,} km. Immediate scheduling required.",
                status=NotificationStatus.SENT,
                related_entity_type="vehicle",
                related_entity_id=str(vehicle.id),
            )
            db.add(notif)
            finding["notification_sent"] = True

        findings.append(finding)

    elif km_remaining <= 2000:
        # Approaching maintenance
        finding = {
            "type": "UPCOMING",
            "fleet_number": vehicle.fleet_number,
            "make": vehicle.make,
            "model": vehicle.model,
            "current_mileage": vehicle.mileage,
            "next_service_mileage": vehicle.next_service_mileage,
            "km_remaining": km_remaining,
            "task_created": False,
            "notification_sent": False,
        }
        # Only create task if not already scheduled
        existing = (
            db.query(MaintenanceTask)
            .filter(
                MaintenanceTask.vehicle_id == vehicle.id,
                MaintenanceTask.status.not_in([TaskStatus.COMPLETED, TaskStatus.CANCELLED]),
                MaintenanceTask.title.like("%Upcoming Service%"),
            )
            .first()
        )
        if not existing:
            task = MaintenanceTask(
                vehicle_id=vehicle.id,
                title=f"Upcoming Service — {vehicle.fleet_number}",
                description=f"Service due in {km_remaining:,} km. Schedule before vehicle reaches {vehicle.next_service_mileage:,} km.",
                severity=IncidentSeverity.MEDIUM,
                status=TaskStatus.APPROVED,
                ai_generated=True,
            )
            db.add(task)
            finding["task_created"] = True

        findings.append(finding)

    return findings
