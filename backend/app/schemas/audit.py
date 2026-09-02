import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel


class AuditLogRead(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID | None
    user_full_name: str | None
    action: str
    entity_type: str
    entity_id: str | None
    details: dict[str, Any] | None
    ip_address: str | None
    created_at: datetime
