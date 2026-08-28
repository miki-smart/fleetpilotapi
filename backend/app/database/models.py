import uuid
from datetime import datetime, date
from enum import Enum as PyEnum
from sqlalchemy import (
    Column, String, Integer, DateTime, Date, Boolean, Text, ForeignKey, Enum, JSON
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, relationship
from sqlalchemy.sql import func


class Base(DeclarativeBase):
    pass


class VehicleStatus(str, PyEnum):
    ACTIVE = "ACTIVE"
    MAINTENANCE_DUE = "MAINTENANCE_DUE"
    OUT_OF_SERVICE = "OUT_OF_SERVICE"


class IncidentSeverity(str, PyEnum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class IncidentStatus(str, PyEnum):
    NEW = "NEW"
    ANALYZING = "ANALYZING"
    AWAITING_APPROVAL = "AWAITING_APPROVAL"
    APPROVED = "APPROVED"
    IN_PROGRESS = "IN_PROGRESS"
    RESOLVED = "RESOLVED"
    REJECTED = "REJECTED"


class TaskStatus(str, PyEnum):
    PENDING_APPROVAL = "PENDING_APPROVAL"
    APPROVED = "APPROVED"
    ASSIGNED = "ASSIGNED"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"


class PartsRequestStatus(str, PyEnum):
    REQUESTED = "REQUESTED"
    ORDERED = "ORDERED"
    RECEIVED = "RECEIVED"
    CANCELLED = "CANCELLED"


class NotificationChannel(str, PyEnum):
    EMAIL = "EMAIL"
    IN_APP = "IN_APP"


class NotificationStatus(str, PyEnum):
    PENDING = "PENDING"
    SENT = "SENT"
    SIMULATED = "SIMULATED"
    FAILED = "FAILED"


class AgentActionType(str, PyEnum):
    ANALYZE_INCIDENT = "ANALYZE_INCIDENT"
    GET_VEHICLE = "GET_VEHICLE"
    GET_MAINTENANCE_HISTORY = "GET_MAINTENANCE_HISTORY"
    DECODE_VIN = "DECODE_VIN"
    CHECK_RECALLS = "CHECK_RECALLS"
    CREATE_MAINTENANCE_TASK = "CREATE_MAINTENANCE_TASK"
    UPDATE_VEHICLE_STATUS = "UPDATE_VEHICLE_STATUS"
    CREATE_PARTS_REQUEST = "CREATE_PARTS_REQUEST"
    SEND_NOTIFICATION = "SEND_NOTIFICATION"
    GET_FLEET_HEALTH = "GET_FLEET_HEALTH"
    GET_UPCOMING_MAINTENANCE = "GET_UPCOMING_MAINTENANCE"
    FLEET_HEALTH_SCAN = "FLEET_HEALTH_SCAN"


class AgentActionStatus(str, PyEnum):
    PENDING = "PENDING"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"


class Vehicle(Base):
    __tablename__ = "vehicles"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    fleet_number = Column(String(20), unique=True, nullable=False, index=True)
    vin = Column(String(17), nullable=True, index=True)
    make = Column(String(50), nullable=False)
    model = Column(String(50), nullable=False)
    year = Column(Integer, nullable=False)
    mileage = Column(Integer, nullable=False)
    status = Column(Enum(VehicleStatus), nullable=False, default=VehicleStatus.ACTIVE)
    fuel_type = Column(String(20), nullable=True, default="Diesel")
    last_service_date = Column(Date, nullable=True)
    next_service_mileage = Column(Integer, nullable=True)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    incidents = relationship("Incident", back_populates="vehicle", lazy="dynamic")
    maintenance_records = relationship("MaintenanceRecord", back_populates="vehicle", lazy="dynamic")
    maintenance_tasks = relationship("MaintenanceTask", back_populates="vehicle", lazy="dynamic")


class MaintenanceRecord(Base):
    __tablename__ = "maintenance_records"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    vehicle_id = Column(UUID(as_uuid=True), ForeignKey("vehicles.id"), nullable=False)
    maintenance_type = Column(String(100), nullable=False)
    description = Column(Text, nullable=True)
    mileage = Column(Integer, nullable=True)
    performed_at = Column(Date, nullable=False)
    status = Column(String(50), nullable=False, default="COMPLETED")
    created_at = Column(DateTime, default=func.now())

    vehicle = relationship("Vehicle", back_populates="maintenance_records")


class Incident(Base):
    __tablename__ = "incidents"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    vehicle_id = Column(UUID(as_uuid=True), ForeignKey("vehicles.id"), nullable=False)
    reported_by = Column(String(100), nullable=False, default="Mechanic")
    description = Column(Text, nullable=False)
    severity = Column(Enum(IncidentSeverity), nullable=True)
    category = Column(String(50), nullable=True)
    status = Column(Enum(IncidentStatus), nullable=False, default=IncidentStatus.NEW)
    ai_analysis = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    vehicle = relationship("Vehicle", back_populates="incidents")
    maintenance_tasks = relationship("MaintenanceTask", back_populates="incident", lazy="dynamic")
    agent_actions = relationship("AgentAction", back_populates="incident", lazy="dynamic")


class MaintenanceTask(Base):
    __tablename__ = "maintenance_tasks"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    vehicle_id = Column(UUID(as_uuid=True), ForeignKey("vehicles.id"), nullable=False)
    incident_id = Column(UUID(as_uuid=True), ForeignKey("incidents.id"), nullable=True)
    title = Column(String(200), nullable=False)
    description = Column(Text, nullable=True)
    severity = Column(Enum(IncidentSeverity), nullable=False)
    status = Column(Enum(TaskStatus), nullable=False, default=TaskStatus.PENDING_APPROVAL)
    assigned_to = Column(String(100), nullable=True)
    due_date = Column(Date, nullable=True)
    ai_generated = Column(Boolean, default=False)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    vehicle = relationship("Vehicle", back_populates="maintenance_tasks")
    incident = relationship("Incident", back_populates="maintenance_tasks")
    parts_requests = relationship("PartsRequest", back_populates="maintenance_task", lazy="dynamic")


class PartsRequest(Base):
    __tablename__ = "parts_requests"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    maintenance_task_id = Column(UUID(as_uuid=True), ForeignKey("maintenance_tasks.id"), nullable=False)
    part_name = Column(String(200), nullable=False)
    quantity = Column(Integer, nullable=False, default=1)
    priority = Column(String(20), nullable=False, default="NORMAL")
    status = Column(Enum(PartsRequestStatus), nullable=False, default=PartsRequestStatus.REQUESTED)
    created_at = Column(DateTime, default=func.now())

    maintenance_task = relationship("MaintenanceTask", back_populates="parts_requests")


class Notification(Base):
    __tablename__ = "notifications"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    recipient = Column(String(200), nullable=False)
    channel = Column(Enum(NotificationChannel), nullable=False, default=NotificationChannel.IN_APP)
    subject = Column(String(300), nullable=False)
    message = Column(Text, nullable=False)
    status = Column(Enum(NotificationStatus), nullable=False, default=NotificationStatus.PENDING)
    related_entity_type = Column(String(50), nullable=True)
    related_entity_id = Column(String(50), nullable=True)
    created_at = Column(DateTime, default=func.now())


class AgentAction(Base):
    __tablename__ = "agent_actions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    incident_id = Column(UUID(as_uuid=True), ForeignKey("incidents.id"), nullable=True)
    action_type = Column(Enum(AgentActionType), nullable=False)
    description = Column(Text, nullable=True)
    status = Column(Enum(AgentActionStatus), nullable=False, default=AgentActionStatus.PENDING)
    tool_name = Column(String(100), nullable=True)
    tool_input = Column(JSON, nullable=True)
    tool_output = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=func.now())
    completed_at = Column(DateTime, nullable=True)

    incident = relationship("Incident", back_populates="agent_actions")
