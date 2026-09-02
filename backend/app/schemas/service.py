import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models.systems import ControlStrategy, ServiceAction, ServiceStatus, ServiceType


class ServiceRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    system_id: uuid.UUID
    server_id: uuid.UUID | None
    name: str
    type: ServiceType
    control_strategy: ControlStrategy
    control_identifier: str | None
    port: int | None
    health_check_url: str | None
    status: ServiceStatus
    last_checked_at: datetime | None


class ServiceCreate(BaseModel):
    system_id: uuid.UUID
    server_id: uuid.UUID | None = None
    name: str
    type: ServiceType
    control_strategy: ControlStrategy
    control_identifier: str | None = None
    port: int | None = None
    health_check_url: str | None = None


class ServiceUpdate(BaseModel):
    server_id: uuid.UUID | None = None
    name: str | None = None
    type: ServiceType | None = None
    control_strategy: ControlStrategy | None = None
    control_identifier: str | None = None
    port: int | None = None
    health_check_url: str | None = None
    status: ServiceStatus | None = None


class ServiceActionRequest(BaseModel):
    action: ServiceAction


class ServiceActionLogRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    service_id: uuid.UUID
    action: ServiceAction
    status: str
    started_at: datetime | None
    finished_at: datetime | None
    output: str | None
