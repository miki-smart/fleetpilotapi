"""
Tests for business rules and severity logic.
These run without a real database by using SQLite in-memory.
"""
import pytest
from unittest.mock import MagicMock, patch
from datetime import date

from app.agents.orchestrator import _apply_business_rules, _parse_analysis
from app.agents.tools import (
    tool_get_vehicle, tool_create_maintenance_task, tool_update_vehicle_status, tool_create_parts_request
)
from app.database.models import (
    Vehicle, MaintenanceTask, VehicleStatus, IncidentSeverity, TaskStatus
)


# --- Business rule tests ---

class TestBusinessRules:
    def test_critical_sets_out_of_service_and_requires_approval(self):
        analysis = {"severity": "CRITICAL", "vehicle_status": "ACTIVE", "requires_manager_approval": False}
        result = _apply_business_rules(analysis)
        assert result["vehicle_status"] == "OUT_OF_SERVICE"
        assert result["requires_manager_approval"] is True

    def test_high_sets_maintenance_due(self):
        analysis = {"severity": "HIGH", "vehicle_status": "ACTIVE", "requires_manager_approval": False}
        result = _apply_business_rules(analysis)
        assert result["vehicle_status"] == "MAINTENANCE_DUE"
        assert result["requires_manager_approval"] is True

    def test_high_does_not_downgrade_out_of_service(self):
        analysis = {"severity": "HIGH", "vehicle_status": "OUT_OF_SERVICE", "requires_manager_approval": False}
        result = _apply_business_rules(analysis)
        assert result["vehicle_status"] == "OUT_OF_SERVICE"

    def test_low_clears_approval_requirement(self):
        analysis = {"severity": "LOW", "vehicle_status": "ACTIVE", "requires_manager_approval": True}
        result = _apply_business_rules(analysis)
        assert result["requires_manager_approval"] is False

    def test_medium_no_forced_changes(self):
        analysis = {"severity": "MEDIUM", "vehicle_status": "ACTIVE", "requires_manager_approval": False}
        result = _apply_business_rules(analysis)
        assert result["vehicle_status"] == "ACTIVE"
        assert result["requires_manager_approval"] is False


# --- AI output parsing tests ---

class TestAnalysisParsing:
    def test_valid_json_parses(self):
        text = '{"category": "BRAKE_SYSTEM", "severity": "CRITICAL", "vehicle_status": "OUT_OF_SERVICE", "summary": "test"}'
        result = _parse_analysis(text)
        assert result is not None
        assert result["category"] == "BRAKE_SYSTEM"
        assert result["severity"] == "CRITICAL"

    def test_json_in_markdown_code_block_parses(self):
        text = '```json\n{"category": "ENGINE", "severity": "HIGH", "vehicle_status": "MAINTENANCE_DUE"}\n```'
        result = _parse_analysis(text)
        assert result is not None
        assert result["severity"] == "HIGH"

    def test_invalid_json_returns_none(self):
        result = _parse_analysis("this is not json at all")
        assert result is None

    def test_missing_severity_returns_none(self):
        result = _parse_analysis('{"category": "ENGINE"}')
        assert result is None

    def test_empty_string_returns_none(self):
        result = _parse_analysis("")
        assert result is None

    def test_none_returns_none(self):
        result = _parse_analysis(None)
        assert result is None


# --- Tool tests with mock DB ---

def _make_mock_vehicle(fleet_number="ET-042", status=VehicleStatus.ACTIVE):
    import uuid
    v = MagicMock(spec=Vehicle)
    v.id = uuid.uuid4()
    v.fleet_number = fleet_number
    v.make = "Toyota"
    v.model = "Hiace"
    v.year = 2021
    v.mileage = 182400
    v.status = status
    v.fuel_type = "Diesel"
    v.last_service_date = date(2024, 3, 15)
    v.next_service_mileage = 190000
    return v


class TestVehicleTool:
    def test_vehicle_found(self):
        db = MagicMock()
        vehicle = _make_mock_vehicle()
        db.query.return_value.filter.return_value.first.return_value = vehicle
        result = tool_get_vehicle("ET-042", db)
        assert result["found"] is True
        assert result["fleet_number"] == "ET-042"

    def test_vehicle_not_found(self):
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = None
        result = tool_get_vehicle("ET-999", db)
        assert result["found"] is False
        assert "error" in result


class TestCreateMaintenanceTask:
    def test_critical_task_requires_approval(self):
        import uuid
        db = MagicMock()
        vehicle = _make_mock_vehicle()
        db.query.return_value.filter.return_value.first.return_value = vehicle
        db.add = MagicMock()
        db.flush = MagicMock()
        result = tool_create_maintenance_task(
            vehicle_id=str(vehicle.id),
            incident_id=None,
            title="Brake Inspection",
            description="Critical brake issue",
            severity="CRITICAL",
            db=db,
        )
        assert result["success"] is True
        assert result["status"] == TaskStatus.PENDING_APPROVAL.value
        assert result["requires_approval"] is True

    def test_low_task_auto_approved(self):
        import uuid
        db = MagicMock()
        vehicle = _make_mock_vehicle()
        db.query.return_value.filter.return_value.first.return_value = vehicle
        db.add = MagicMock()
        db.flush = MagicMock()
        result = tool_create_maintenance_task(
            vehicle_id=str(vehicle.id),
            incident_id=None,
            title="Tire Rotation",
            description="Routine tire rotation",
            severity="LOW",
            db=db,
        )
        assert result["success"] is True
        assert result["status"] == TaskStatus.APPROVED.value
        assert result["requires_approval"] is False

    def test_invalid_severity_returns_error(self):
        import uuid
        db = MagicMock()
        vehicle = _make_mock_vehicle()
        db.query.return_value.filter.return_value.first.return_value = vehicle
        result = tool_create_maintenance_task(
            vehicle_id=str(vehicle.id),
            incident_id=None,
            title="Test",
            description="Test",
            severity="INVALID_SEVERITY",
            db=db,
        )
        assert result["success"] is False

    def test_vehicle_not_found_returns_error(self):
        import uuid
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = None
        result = tool_create_maintenance_task(
            vehicle_id=str(uuid.uuid4()),
            incident_id=None,
            title="Test",
            description="Test",
            severity="MEDIUM",
            db=db,
        )
        assert result["success"] is False


class TestUpdateVehicleStatus:
    def test_status_update_success(self):
        db = MagicMock()
        vehicle = _make_mock_vehicle()
        db.query.return_value.filter.return_value.first.return_value = vehicle
        result = tool_update_vehicle_status(str(vehicle.id), "OUT_OF_SERVICE", db)
        assert result["success"] is True
        assert result["new_status"] == "OUT_OF_SERVICE"

    def test_invalid_status(self):
        db = MagicMock()
        vehicle = _make_mock_vehicle()
        db.query.return_value.filter.return_value.first.return_value = vehicle
        result = tool_update_vehicle_status(str(vehicle.id), "BROKEN", db)
        assert result["success"] is False
