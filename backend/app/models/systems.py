import enum
import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPKMixin

if TYPE_CHECKING:
    from app.models.infrastructure import Server


class SystemCriticality(str, enum.Enum):
    low = "low"
    medium = "medium"
    high = "high"
    critical = "critical"


class SystemStatus(str, enum.Enum):
    active = "active"
    maintenance = "maintenance"
    retired = "retired"


class ServiceType(str, enum.Enum):
    frontend = "frontend"
    backend = "backend"
    database = "database"
    cache = "cache"
    proxy = "proxy"
    windows_service = "windows_service"
    pm2_process = "pm2_process"
    ftp = "ftp"
    smtp = "smtp"
    cron_job = "cron_job"
    other = "other"


class ControlStrategy(str, enum.Enum):
    systemd = "systemd"
    windows_service = "windows_service"
    pm2 = "pm2"
    docker = "docker"
    script = "script"


class ServiceStatus(str, enum.Enum):
    running = "running"
    stopped = "stopped"
    degraded = "degraded"
    unknown = "unknown"


class ServiceAction(str, enum.Enum):
    start = "start"
    stop = "stop"
    restart = "restart"
    force_restart = "force_restart"


class ActionResultStatus(str, enum.Enum):
    pending = "pending"
    success = "success"
    failed = "failed"


class System(Base, UUIDPKMixin, TimestampMixin):
    __tablename__ = "systems"

    name: Mapped[str] = mapped_column(String(150), nullable=False)
    slug: Mapped[str] = mapped_column(String(150), unique=True, nullable=False, index=True)
    description: Mapped[str | None] = mapped_column(Text)
    category: Mapped[str | None] = mapped_column(String(100))
    criticality: Mapped[SystemCriticality] = mapped_column(
        Enum(SystemCriticality, name="system_criticality"), default=SystemCriticality.medium, nullable=False
    )
    status: Mapped[SystemStatus] = mapped_column(
        Enum(SystemStatus, name="system_status"), default=SystemStatus.active, nullable=False
    )
    owner_user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))
    repo_url: Mapped[str | None] = mapped_column(String(500))
    default_branch: Mapped[str | None] = mapped_column(String(100), default="main")
    repo_local_path: Mapped[str | None] = mapped_column(String(500))
    deploy_build_command: Mapped[str | None] = mapped_column(Text)

    services: Mapped[list["Service"]] = relationship(back_populates="system", cascade="all, delete-orphan")


class Service(Base, UUIDPKMixin, TimestampMixin):
    __tablename__ = "services"
    __table_args__ = (UniqueConstraint("system_id", "name", name="uq_service_system_name"),)

    system_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("systems.id", ondelete="CASCADE"), nullable=False, index=True
    )
    server_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("servers.id"), nullable=True, index=True
    )
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    type: Mapped[ServiceType] = mapped_column(Enum(ServiceType, name="service_type"), nullable=False)
    control_strategy: Mapped[ControlStrategy] = mapped_column(
        Enum(ControlStrategy, name="control_strategy"), nullable=False
    )
    control_identifier: Mapped[str | None] = mapped_column(String(255))
    port: Mapped[int | None] = mapped_column(Integer)
    health_check_url: Mapped[str | None] = mapped_column(String(500))
    status: Mapped[ServiceStatus] = mapped_column(
        Enum(ServiceStatus, name="service_status"), default=ServiceStatus.unknown, nullable=False
    )
    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    system: Mapped["System"] = relationship(back_populates="services")
    server: Mapped["Server | None"] = relationship(back_populates="services")


class ServiceDependency(Base, UUIDPKMixin):
    __tablename__ = "service_dependencies"
    __table_args__ = (UniqueConstraint("service_id", "depends_on_service_id", name="uq_service_dependency"),)

    service_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("services.id", ondelete="CASCADE"), nullable=False, index=True
    )
    depends_on_service_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("services.id", ondelete="CASCADE"), nullable=False, index=True
    )
    dependency_type: Mapped[str | None] = mapped_column(String(100))


class ServiceActionLog(Base, UUIDPKMixin):
    __tablename__ = "service_action_logs"

    service_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("services.id", ondelete="CASCADE"), nullable=False, index=True
    )
    action: Mapped[ServiceAction] = mapped_column(Enum(ServiceAction, name="service_action"), nullable=False)
    triggered_by_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))
    status: Mapped[ActionResultStatus] = mapped_column(
        Enum(ActionResultStatus, name="action_result_status"), default=ActionResultStatus.pending, nullable=False
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    output: Mapped[str | None] = mapped_column(Text)
