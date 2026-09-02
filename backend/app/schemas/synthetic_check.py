import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict


class SyntheticCheckResultRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    service_id: uuid.UUID
    prober_server_id: uuid.UUID | None
    prober_hostname: str | None = None
    success: bool
    status_code: int | None
    latency_ms: float | None
    error_message: str | None
    checked_at: datetime


SyntheticOverallStatus = Literal["up", "degraded", "down", "unknown"]


class SyntheticProberStatus(BaseModel):
    prober_server_id: uuid.UUID | None
    prober_hostname: str | None
    success: bool
    status_code: int | None
    latency_ms: float | None
    error_message: str | None
    checked_at: datetime
    uptime_percent: float | None


class SyntheticCheckSummary(BaseModel):
    service_id: uuid.UUID
    service_name: str
    system_id: uuid.UUID
    system_name: str
    health_check_url: str
    server_id: uuid.UUID | None
    hostname: str | None
    site_id: uuid.UUID | None
    site_name: str | None
    overall_status: SyntheticOverallStatus
    uptime_percent: float | None
    avg_latency_ms: float | None
    probers: list[SyntheticProberStatus]
