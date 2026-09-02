import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, model_validator

from app.models.monitoring import MaintenanceScope
from app.services.maintenance_windows import MaintenanceStatus


class MaintenanceWindowCreate(BaseModel):
    scope_type: MaintenanceScope
    scope_id: uuid.UUID
    reason: str
    description: str | None = None
    starts_at: datetime
    ends_at: datetime

    @model_validator(mode="after")
    def _check_range(self) -> "MaintenanceWindowCreate":
        if self.ends_at <= self.starts_at:
            raise ValueError("ends_at debe ser posterior a starts_at")
        return self


class MaintenanceWindowUpdate(BaseModel):
    reason: str | None = None
    description: str | None = None
    ends_at: datetime | None = None


class MaintenanceWindowRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    scope_type: MaintenanceScope
    scope_id: uuid.UUID
    scope_label: str
    reason: str
    description: str | None
    starts_at: datetime
    ends_at: datetime
    cancelled_at: datetime | None
    status: MaintenanceStatus
    created_by_id: uuid.UUID | None
    created_by_name: str | None
    created_at: datetime
