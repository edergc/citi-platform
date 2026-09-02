import uuid
from datetime import datetime

from pydantic import BaseModel


class OfflineServerBrief(BaseModel):
    id: uuid.UUID
    hostname: str
    status: str


class OpenAlertBrief(BaseModel):
    id: uuid.UUID
    hostname: str | None
    rule_name: str
    severity: str
    value: float | None
    acknowledged: bool


class FailedBackupBrief(BaseModel):
    id: uuid.UUID
    service_name: str
    type: str
    error_message: str | None
    started_at: datetime | None


class WeeklyReportRead(BaseModel):
    site_id: uuid.UUID | None
    site_name: str | None
    window_start: datetime
    window_end: datetime
    servers_total: int
    servers_online: int
    servers_offline: int
    offline_servers: list[OfflineServerBrief]
    open_alerts_by_severity: dict[str, int]
    unacknowledged_open_alerts: int
    open_alerts: list[OpenAlertBrief]
    backup_failures: int
    failed_backups: list[FailedBackupBrief]
