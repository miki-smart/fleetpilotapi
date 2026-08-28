from pydantic import BaseModel, Field
from typing import Optional
from enum import Enum


class IncidentCategory(str, Enum):
    BRAKE_SYSTEM = "BRAKE_SYSTEM"
    ENGINE = "ENGINE"
    TRANSMISSION = "TRANSMISSION"
    ELECTRICAL = "ELECTRICAL"
    SUSPENSION = "SUSPENSION"
    COOLING_SYSTEM = "COOLING_SYSTEM"
    FUEL_SYSTEM = "FUEL_SYSTEM"
    EXHAUST = "EXHAUST"
    TIRES = "TIRES"
    BODY_DAMAGE = "BODY_DAMAGE"
    GENERAL_MAINTENANCE = "GENERAL_MAINTENANCE"
    UNKNOWN = "UNKNOWN"


class RequiredPart(BaseModel):
    name: str
    quantity: int = 1


class IncidentAnalysis(BaseModel):
    """Validated shape of the model's final verdict. The orchestrator normalizes the raw
    tool arguments into this before anything is persisted."""
    category: IncidentCategory
    severity: str = Field(..., description="LOW | MEDIUM | HIGH | CRITICAL")
    vehicle_status: str = Field(..., description="ACTIVE | MAINTENANCE_DUE | OUT_OF_SERVICE")
    summary: str = Field(default="", description="Clear summary of the issue and recommended immediate action")
    possible_causes: list[str] = Field(default_factory=list)
    recommended_actions: list[str] = Field(default_factory=list)
    required_parts: list[RequiredPart] = Field(default_factory=list)
    related_recalls: list[str] = Field(default_factory=list)
    requires_manager_approval: bool = False


class AgentToolResult(BaseModel):
    tool_name: str
    success: bool
    data: Optional[dict] = None
    error: Optional[str] = None
