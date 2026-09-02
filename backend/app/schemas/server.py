import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, field_validator

from app.models.infrastructure import AgentStatus, OSType, ServerStatus
from app.models.monitoring import MaintenanceScope

ServerHealth = Literal["ok", "warning", "critical"]

# Fixed vocabulary for "para qué se usa este servidor" — admin checks/unchecks these per
# server (see SERVIDORES_2026.xlsx's "USO: EN CHECK: ..." column, which is where this list
# came from). Deliberately closed rather than freeform tags, so the checkboxes in the UI
# always match what's actually storable.
SERVER_USAGE_TAGS: tuple[str, ...] = (
    "SINOE",
    "EJE",
    "NCPP",
    "VISOR",
    "SIGRA",
    "REPOSITORIO",
    "WSUS",
    "DHCP",
    "ANTIVIRUS",
)
ServerUsageTag = Literal[
    "SINOE", "EJE", "NCPP", "VISOR", "SIGRA", "REPOSITORIO", "WSUS", "DHCP", "ANTIVIRUS"
]


class MaintenanceWindowBrief(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    scope_type: MaintenanceScope
    reason: str
    ends_at: datetime


class ServerRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    site_id: uuid.UUID | None
    hostname: str
    ip_address: str | None

    @field_validator("ip_address", mode="before")
    @classmethod
    def _stringify_ip(cls, v: object) -> str | None:
        return None if v is None else str(v)
    os_type: OSType
    os_version: str | None
    cpu_cores: int | None
    ram_mb: int | None
    disk_gb: int | None
    status: ServerStatus
    created_at: datetime
    usage_tags: list[str] = []

    @field_validator("usage_tags", mode="before")
    @classmethod
    def _default_usage_tags(cls, v: object) -> object:
        return [] if v is None else v
    primary_responsible_user_id: uuid.UUID | None = None
    primary_responsible_user_name: str | None = None
    health: ServerHealth = "ok"
    health_reasons: list[str] = []
    active_maintenance: MaintenanceWindowBrief | None = None
    is_synthetic_probe: bool = False


class ServerCreate(BaseModel):
    site_id: uuid.UUID | None = None
    hostname: str
    ip_address: str | None = None
    os_type: OSType
    os_version: str | None = None
    cpu_cores: int | None = None
    ram_mb: int | None = None
    disk_gb: int | None = None
    usage_tags: list[ServerUsageTag] = []
    primary_responsible_user_id: uuid.UUID | None = None
    is_synthetic_probe: bool = False


class ServerUpdate(BaseModel):
    site_id: uuid.UUID | None = None
    hostname: str | None = None
    ip_address: str | None = None
    os_type: OSType | None = None
    os_version: str | None = None
    cpu_cores: int | None = None
    ram_mb: int | None = None
    disk_gb: int | None = None
    status: ServerStatus | None = None
    usage_tags: list[ServerUsageTag] | None = None
    primary_responsible_user_id: uuid.UUID | None = None
    is_synthetic_probe: bool | None = None


class DiskMetric(BaseModel):
    mount: str
    total_gb: float
    free_gb: float
    percent_used: float
    inode_total: int | None = None
    inode_used_percent: float | None = None


class ProcessMetric(BaseModel):
    pid: int
    name: str | None
    cpu_percent: float
    ram_mb: int


class DiskHealthInfo(BaseModel):
    device: str
    type: str
    power_on_hours: float | None = None
    smart_passed: bool | None = None
    wearout_percent: float | None = None
    temperature_c: float | None = None
    error_count: int | None = None


class DiskIoInfo(BaseModel):
    device: str
    read_mbps: float
    write_mbps: float


class PortConnectionInfo(BaseModel):
    port: int
    connection_count: int


class ServerMetricsRead(BaseModel):
    agent_status: AgentStatus | None
    last_heartbeat_at: datetime | None
    metrics_updated_at: datetime | None
    cpu_percent: float | None
    ram_total_mb: int | None
    ram_used_mb: int | None
    ram_percent: float | None
    disks: list[DiskMetric] | None
    net_bytes_sent: int | None
    net_bytes_recv: int | None
    uptime_seconds: int | None
    net_sent_rate_mbps: float | None
    net_recv_rate_mbps: float | None
    disk_read_mbps: float | None
    disk_write_mbps: float | None
    disk_io: list[DiskIoInfo] | None
    top_cpu_processes: list[ProcessMetric] | None
    top_ram_processes: list[ProcessMetric] | None
    port_connections: list[PortConnectionInfo] | None
    processes_updated_at: datetime | None
    agent_version: str | None
    kernel_version: str | None
    cpu_model: str | None
    load_average_1m: float | None
    disk_health: list[DiskHealthInfo] | None
    disk_health_available: bool | None


class ServerNoteRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    server_id: uuid.UUID
    author_id: uuid.UUID | None
    author_name: str | None = None
    body: str
    created_at: datetime


class ServerNoteCreate(BaseModel):
    body: str


class ServerEventRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    server_id: uuid.UUID
    log_name: str
    event_record_id: int
    level: int
    provider: str | None
    event_id: int | None
    message: str | None
    occurred_at: datetime
    received_at: datetime


class SiteUserBrief(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    full_name: str


class ServerMetricHistoryPoint(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    recorded_at: datetime
    cpu_percent: float | None
    ram_percent: float | None
    disk_percent_used: float | None
    net_bytes_sent: int | None
    net_bytes_recv: int | None


class DiskForecast(BaseModel):
    sample_days: int
    sample_count: int
    current_percent: float | None
    trend_percent_per_day: float | None
    days_until_full: float | None


class ServerOutage(BaseModel):
    started_at: datetime
    ended_at: datetime | None
    duration_seconds: int


class ServerUptimeSummary(BaseModel):
    window_days: int
    uptime_percent: float
    outages: list[ServerOutage]


class FleetConnectivityEvent(BaseModel):
    id: str
    server_id: uuid.UUID
    hostname: str
    site_id: uuid.UUID | None
    site_name: str | None
    event_type: Literal["disconnected", "reconnected"]
    occurred_at: datetime
    message: str


class CriticalConnectivityAlert(BaseModel):
    id: uuid.UUID
    server_id: uuid.UUID
    hostname: str
    site_name: str | None
    occurred_at: datetime
    message: str


class ServerConnectivitySummary(BaseModel):
    server_id: uuid.UUID
    hostname: str
    site_id: uuid.UUID | None
    site_name: str | None
    status: ServerStatus
    uptime_percent: float | None
    outage_count: int
    last_event_type: Literal["disconnected", "reconnected"] | None
    last_event_at: datetime | None
    last_event_message: str | None


class ServerSparklinePoint(BaseModel):
    recorded_at: datetime
    cpu_percent: float | None
    ram_percent: float | None


class ServerSparkline(BaseModel):
    server_id: uuid.UUID
    points: list[ServerSparklinePoint]


class ServerActivityItem(BaseModel):
    kind: str
    occurred_at: datetime
    title: str
    detail: str | None
    status: str


class FleetStatusCounts(BaseModel):
    online: int
    offline: int
    degraded: int
    unknown: int


class FleetAgentStatusCounts(BaseModel):
    pending: int
    active: int
    revoked: int
    unreachable: int


class SiteAverage(BaseModel):
    site_id: uuid.UUID | None
    site_name: str | None
    server_count: int


class BreachingServer(BaseModel):
    server_id: uuid.UUID
    hostname: str
    site_name: str | None
    rule_name: str
    metric: str
    mount: str | None
    severity: str
    value: float
    threshold: float


class FleetSummary(BaseModel):
    status_counts: FleetStatusCounts
    agent_status_counts: FleetAgentStatusCounts
    site_averages: list[SiteAverage]
    breaching_servers: list[BreachingServer]
