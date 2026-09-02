import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class ConfigEntryCreate(BaseModel):
    service_id: uuid.UUID
    environment_code: str
    key: str
    value: str
    is_secret: bool = False
    description: str | None = None


class ConfigEntryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    service_id: uuid.UUID
    key: str
    value: str | None
    is_secret: bool
    description: str | None
    version: int
    updated_at: datetime


class ConfigEntryHistoryRead(BaseModel):
    id: uuid.UUID
    previous_value: str | None
    changed_at: datetime
