from datetime import datetime

from pydantic import BaseModel


class PublicSystemStatus(BaseModel):
    name: str
    category: str | None
    status: str
    last_checked_at: datetime | None


class PublicServerStatus(BaseModel):
    hostname: str
    site_name: str | None
    status: str
    last_heartbeat_at: datetime | None
