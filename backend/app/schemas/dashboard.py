import uuid
from datetime import date, datetime

from pydantic import BaseModel

from app.models.monitoring import MaintenanceScope


class OsComparison(BaseModel):
    os_type: str
    server_count: int
    ok_count: int
    warning_count: int
    critical_count: int
    avg_cpu_percent: float | None
    avg_ram_percent: float | None
    avg_uptime_percent: float | None


class SiteRanking(BaseModel):
    site_id: uuid.UUID
    site_name: str
    server_count: int
    ok_count: int
    warning_count: int
    critical_count: int
    avg_cpu_percent: float | None
    avg_ram_percent: float | None
    avg_uptime_percent: float | None
    avg_network_score: float | None
    open_alerts: int
    servers_in_maintenance: int


class AlertTrendPoint(BaseModel):
    week_start: date
    critical: int
    warning: int
    info: int


class TopOffender(BaseModel):
    server_id: uuid.UUID
    hostname: str
    site_name: str | None
    value: float


class MaintenanceFleetItem(BaseModel):
    id: uuid.UUID
    scope_type: MaintenanceScope
    scope_label: str
    reason: str
    starts_at: datetime
    ends_at: datetime


class MaintenanceSummary(BaseModel):
    active_count: int
    scheduled_count: int
    active: list[MaintenanceFleetItem]


class FleetDashboard(BaseModel):
    os_comparison: list[OsComparison]
    site_ranking: list[SiteRanking]
    alert_trend: list[AlertTrendPoint]
    worst_uptime: list[TopOffender]
    most_alerts: list[TopOffender]
    highest_cpu: list[TopOffender]
    highest_ram: list[TopOffender]
    worst_network: list[TopOffender]
    maintenance: MaintenanceSummary
