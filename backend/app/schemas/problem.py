import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel

from app.models.monitoring import AlertSeverity

ProblemKind = Literal[
    "alert", "server_offline", "server_degraded", "service_degraded", "backup_failed", "deploy_failed", "synthetic_failed"
]


class ProblemRow(BaseModel):
    id: str
    kind: ProblemKind
    severity: AlertSeverity
    title: str
    detail: str | None
    server_id: uuid.UUID | None
    hostname: str | None
    site_id: uuid.UUID | None
    site_name: str | None
    system_id: uuid.UUID | None
    system_name: str | None
    occurred_at: datetime
    during_maintenance: bool
    alert_event_id: uuid.UUID | None = None
    acknowledged_at: datetime | None = None
