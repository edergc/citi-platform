import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict

from app.models.monitoring import NotificationChannelType, NotificationStatus


class NotificationChannelCreate(BaseModel):
    type: NotificationChannelType
    name: str
    config: dict[str, Any]
    enabled: bool = True


class NotificationChannelUpdate(BaseModel):
    name: str | None = None
    config: dict[str, Any] | None = None
    enabled: bool | None = None


class NotificationChannelRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    type: NotificationChannelType
    name: str
    enabled: bool
    created_at: datetime


class NotificationTestRequest(BaseModel):
    to: str
    message: str = "Mensaje de prueba desde CITI Platform."


class NotificationLogRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    channel_id: uuid.UUID
    alert_event_id: uuid.UUID | None
    sent_at: datetime
    status: NotificationStatus
    error_message: str | None


class NotificationLogPage(BaseModel):
    items: list[NotificationLogRead]
    total: int
