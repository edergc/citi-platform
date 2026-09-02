import enum
import uuid
from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, Enum, Float, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import INET, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPKMixin


class OSType(str, enum.Enum):
    linux = "linux"
    windows = "windows"


class ServerStatus(str, enum.Enum):
    online = "online"
    offline = "offline"
    degraded = "degraded"
    unknown = "unknown"


class AgentStatus(str, enum.Enum):
    pending = "pending"
    active = "active"
    revoked = "revoked"
    unreachable = "unreachable"


class NetworkDeviceType(str, enum.Enum):
    switch = "switch"
    router = "router"
    firewall = "firewall"
    nas = "nas"
    ups = "ups"


class Site(Base, UUIDPKMixin, TimestampMixin):
    __tablename__ = "sites"

    name: Mapped[str] = mapped_column(String(150), nullable=False)
    code: Mapped[str] = mapped_column(String(30), unique=True, nullable=False)
    address: Mapped[str | None] = mapped_column(String(255))
    timezone: Mapped[str] = mapped_column(String(50), default="America/Lima", nullable=False)

    servers: Mapped[list["Server"]] = relationship(back_populates="site")
    users: Mapped[list["User"]] = relationship(secondary="user_sites", back_populates="sites")


class Server(Base, UUIDPKMixin, TimestampMixin):
    __tablename__ = "servers"

    site_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("sites.id"), index=True)
    hostname: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    ip_address: Mapped[str | None] = mapped_column(INET)
    os_type: Mapped[OSType] = mapped_column(Enum(OSType, name="os_type"), nullable=False)
    os_version: Mapped[str | None] = mapped_column(String(100))
    cpu_cores: Mapped[int | None] = mapped_column(Integer)
    ram_mb: Mapped[int | None] = mapped_column(Integer)
    disk_gb: Mapped[int | None] = mapped_column(Integer)
    status: Mapped[ServerStatus] = mapped_column(
        Enum(ServerStatus, name="server_status"), default=ServerStatus.unknown, nullable=False
    )
    tags: Mapped[dict | None] = mapped_column(JSONB)
    # Which institutional systems this server is checked in for (SINOE, EJE, NCPP, etc.) —
    # a fixed, curated vocabulary (see app.schemas.server.SERVER_USAGE_TAGS), unlike the
    # freeform `tags` dict above. Admin-editable checkboxes in the UI.
    usage_tags: Mapped[list[str] | None] = mapped_column(JSONB)
    primary_responsible_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    # Marks this server's Agent as a synthetic-check vantage point — see
    # app.services.synthetic_checks. Admin picks a handful of representative servers
    # (one per key sede), not every server, to keep check fan-out small.
    is_synthetic_probe: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    site: Mapped["Site"] = relationship(back_populates="servers")
    agent: Mapped["Agent | None"] = relationship(back_populates="server", uselist=False, passive_deletes=True)
    services: Mapped[list["Service"]] = relationship(back_populates="server")
    primary_responsible_user: Mapped["User | None"] = relationship(foreign_keys=[primary_responsible_user_id])


class Agent(Base, UUIDPKMixin, TimestampMixin):
    __tablename__ = "agents"

    server_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("servers.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    version: Mapped[str | None] = mapped_column(String(50))
    cert_fingerprint: Mapped[str | None] = mapped_column(String(255))
    enrollment_token_hash: Mapped[str | None] = mapped_column(String(255))
    status: Mapped[AgentStatus] = mapped_column(
        Enum(AgentStatus, name="agent_status"), default=AgentStatus.pending, nullable=False
    )
    last_heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    enrolled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Latest metrics snapshot, updated on every heartbeat (~15s). See ServerMetricHistory
    # for the retained rolling history used for trend charts.
    cpu_percent: Mapped[float | None] = mapped_column(Float)
    ram_total_mb: Mapped[int | None] = mapped_column(Integer)
    ram_used_mb: Mapped[int | None] = mapped_column(Integer)
    ram_percent: Mapped[float | None] = mapped_column(Float)
    disks: Mapped[list | None] = mapped_column(JSONB)
    net_bytes_sent: Mapped[int | None] = mapped_column(BigInteger)
    net_bytes_recv: Mapped[int | None] = mapped_column(BigInteger)
    uptime_seconds: Mapped[int | None] = mapped_column(BigInteger)
    metrics_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Current throughput (computed by the agent as a delta between samples, not
    # cumulative like net_bytes_sent/recv above) and a snapshot of the heaviest
    # processes — refreshed every ~60s by the agent, not every heartbeat.
    net_sent_rate_mbps: Mapped[float | None] = mapped_column(Float)
    net_recv_rate_mbps: Mapped[float | None] = mapped_column(Float)
    disk_read_mbps: Mapped[float | None] = mapped_column(Float)
    disk_write_mbps: Mapped[float | None] = mapped_column(Float)
    top_cpu_processes: Mapped[list | None] = mapped_column(JSONB)
    top_ram_processes: Mapped[list | None] = mapped_column(JSONB)
    processes_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Static-ish system info, refreshed on every heartbeat but rarely actually changes —
    # `version` above is the CITI agent's own software version (existing column, was
    # never populated until now); these are about the host it's running on.
    kernel_version: Mapped[str | None] = mapped_column(String(100))
    cpu_model: Mapped[str | None] = mapped_column(String(255))
    load_average_1m: Mapped[float | None] = mapped_column(Float)

    # Physical disk health (SMART) — a slow-changing snapshot like `disks` above, not a
    # retained history table: wear/power-on-hours move over weeks, not something worth
    # charting hour-by-hour. Refreshed roughly every 30 min by the agent (see
    # SMART_CHECK_INTERVAL_SECONDS in citi_agent.py), only when a fresh sample is ready
    # — None until the agent's first successful cycle, or forever on hosts where
    # smartctl isn't installed (see the "available" flag inside the payload itself).
    disk_health: Mapped[dict | None] = mapped_column(JSONB)

    # Both refreshed on their own cadence by the agent — disk_io every heartbeat (like
    # the aggregate disk_read_mbps/write_mbps above, just broken out per physical
    # device), port_connections every ~60s alongside top_cpu_processes/top_ram_processes.
    disk_io: Mapped[list | None] = mapped_column(JSONB)
    port_connections: Mapped[list | None] = mapped_column(JSONB)

    server: Mapped["Server"] = relationship(back_populates="agent")


class ServerMetricHistory(Base, UUIDPKMixin):
    """Rolling metrics history for trend charts. One row roughly every few minutes per
    server (throttled in the heartbeat handler, not every 15s heartbeat) — pruned by the
    same background retention loop as backups (see app/services/metrics_retention.py)."""

    __tablename__ = "server_metric_history"

    server_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("servers.id", ondelete="CASCADE"), nullable=False, index=True
    )
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )
    cpu_percent: Mapped[float | None] = mapped_column(Float)
    ram_percent: Mapped[float | None] = mapped_column(Float)
    disk_percent_used: Mapped[float | None] = mapped_column(Float)
    net_bytes_sent: Mapped[int | None] = mapped_column(BigInteger)
    net_bytes_recv: Mapped[int | None] = mapped_column(BigInteger)


class ServerNetworkPathHistory(Base, UUIDPKMixin):
    """One row per network-path probe cycle (~60s, see agent's network_path_loop), not
    one row per hop — a JSONB hops list follows the same convention already used for
    Agent.disks/top_cpu_processes, keeps row volume manageable across the fleet, and
    sidesteps needing a dedup key for a hop count that can vary slightly between
    cycles. Pruned on a shorter window than ServerMetricHistory (see
    app/services/metrics_retention.py) — this is recent diagnostic detail, not a
    long-term capacity trend."""

    __tablename__ = "server_network_path_history"

    server_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("servers.id", ondelete="CASCADE"), nullable=False, index=True
    )
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )
    target: Mapped[str] = mapped_column(String(255), nullable=False)
    reachable: Mapped[bool] = mapped_column(Boolean, nullable=False)
    hops: Mapped[list] = mapped_column(JSONB, nullable=False)


class ServerNote(Base, UUIDPKMixin):
    """Append-only logbook entry for a server — deliberately no update/delete: it's a
    record of who documented what and when, not a mutable notes field."""

    __tablename__ = "server_notes"

    server_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("servers.id", ondelete="CASCADE"), nullable=False, index=True
    )
    author_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))
    body: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )

    author: Mapped["User | None"] = relationship()


class ServerEvent(Base, UUIDPKMixin):
    """Durable history of critical Windows Event Log entries (System/Application,
    Level 1=Critical or 2=Error) reported by the agent — for review, not alerting (see
    app.api.v1.agents's heartbeat handler). Deduplicated per (server, log, record id)
    since the agent's in-memory watermark resets on restart and may re-poll a few
    already-seen records."""

    __tablename__ = "server_events"
    __table_args__ = (UniqueConstraint("server_id", "log_name", "event_record_id", name="uq_server_events_dedup"),)

    server_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("servers.id", ondelete="CASCADE"), nullable=False, index=True
    )
    log_name: Mapped[str] = mapped_column(String(50), nullable=False)
    event_record_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    level: Mapped[int] = mapped_column(Integer, nullable=False)
    provider: Mapped[str | None] = mapped_column(String(255))
    event_id: Mapped[int | None] = mapped_column(Integer)
    message: Mapped[str | None] = mapped_column(Text)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class NetworkDevice(Base, UUIDPKMixin, TimestampMixin):
    __tablename__ = "network_devices"

    site_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("sites.id"), index=True)
    type: Mapped[NetworkDeviceType] = mapped_column(Enum(NetworkDeviceType, name="network_device_type"), nullable=False)
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    ip_address: Mapped[str | None] = mapped_column(INET)
    vendor: Mapped[str | None] = mapped_column(String(100))
    model: Mapped[str | None] = mapped_column(String(100))
    status: Mapped[ServerStatus] = mapped_column(
        Enum(ServerStatus, name="server_status"), default=ServerStatus.unknown, nullable=False
    )
