import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict

from app.models.docs import DependencyType


class LicenseCreate(BaseModel):
    name: str
    vendor: str | None = None
    system_id: uuid.UUID | None = None
    server_id: uuid.UUID | None = None
    expiry_date: date | None = None
    seats: int | None = None
    cost: float | None = None
    notes: str | None = None


class LicenseUpdate(BaseModel):
    name: str | None = None
    vendor: str | None = None
    expiry_date: date | None = None
    seats: int | None = None
    cost: float | None = None
    notes: str | None = None


class LicenseRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    vendor: str | None
    system_id: uuid.UUID | None
    server_id: uuid.UUID | None
    expiry_date: date | None
    seats: int | None
    cost: float | None
    notes: str | None
    created_at: datetime


class DependencyCreate(BaseModel):
    system_id: uuid.UUID
    name: str
    type: DependencyType
    version: str | None = None
    criticality: str | None = None
    notes: str | None = None


class DependencyRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    system_id: uuid.UUID
    name: str
    type: DependencyType
    version: str | None
    criticality: str | None
    notes: str | None
