from fastapi import HTTPException, status


class FleetPilotError(Exception):
    def __init__(self, code: str, message: str, status_code: int = 500):
        self.code = code
        self.message = message
        self.status_code = status_code
        super().__init__(message)


class VehicleNotFoundError(FleetPilotError):
    def __init__(self, identifier: str):
        super().__init__(
            code="VEHICLE_NOT_FOUND",
            message=f"Vehicle '{identifier}' was not found.",
            status_code=404,
        )


class IncidentNotFoundError(FleetPilotError):
    def __init__(self, incident_id: str):
        super().__init__(
            code="INCIDENT_NOT_FOUND",
            message=f"Incident '{incident_id}' was not found.",
            status_code=404,
        )


class MaintenanceTaskNotFoundError(FleetPilotError):
    def __init__(self, task_id: str):
        super().__init__(
            code="TASK_NOT_FOUND",
            message=f"Maintenance task '{task_id}' was not found.",
            status_code=404,
        )


class AIAnalysisError(FleetPilotError):
    def __init__(self, message: str = "AI analysis failed"):
        super().__init__(
            code="AI_ANALYSIS_FAILED",
            message=message,
            status_code=502,
        )


class ValidationError(FleetPilotError):
    def __init__(self, message: str):
        super().__init__(
            code="VALIDATION_ERROR",
            message=message,
            status_code=422,
        )
