import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class InAppNotificationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    severity: str
    title: str
    message: str
    entity_type: str | None
    entity_id: str | None
    read_at: datetime | None
    created_at: datetime


class UnreadCountResponse(BaseModel):
    count: int
