import enum
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPKMixin


class AlertScope(str, enum.Enum):
    server = "server"
    service = "service"
    system = "system"


class AlertCondition(str, enum.Enum):
    gt = "gt"
    lt = "lt"
    gte = "gte"
    lte = "lte"
    eq = "eq"


class AlertSeverity(str, enum.Enum):
    info = "info"
    warning = "warning"
    critical = "critical"


class AlertEventStatus(str, enum.Enum):
    open = "open"
    resolved = "resolved"


class MaintenanceScope(str, enum.Enum):
    server = "server"
    site = "site"


class NotificationChannelType(str, enum.Enum):
    email = "email"
    telegram = "telegram"
    whatsapp = "whatsapp"
    teams = "teams"


class NotificationStatus(str, enum.Enum):
    sent = "sent"
    failed = "failed"


class AlertRule(Base, UUIDPKMixin, TimestampMixin):
    """Admin-configurable threshold rule (RAM/CPU/disk) evaluated on every agent heartbeat
    — see app.services.metric_thresholds. scope_id=NULL means the rule applies to every
    server of scope_type (a "global" rule), rather than one specific server."""

    __tablename__ = "alert_rules"

    name: Mapped[str] = mapped_column(String(150), nullable=False)
    scope_type: Mapped[AlertScope] = mapped_column(Enum(AlertScope, name="alert_scope"), nullable=False)
    scope_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), index=True)
    metric: Mapped[str] = mapped_column(String(100), nullable=False)
    metric_target: Mapped[str | None] = mapped_column(String(255))
    condition: Mapped[AlertCondition] = mapped_column(Enum(AlertCondition, name="alert_condition"), nullable=False)
    threshold: Mapped[float] = mapped_column(Float, nullable=False)
    severity: Mapped[AlertSeverity] = mapped_column(
        Enum(AlertSeverity, name="alert_severity"), default=AlertSeverity.warning, nullable=False
    )
    custom_message: Mapped[str | None] = mapped_column(Text)
    cooldown_minutes: Mapped[int] = mapped_column(Integer, default=30, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    events: Mapped[list["AlertEvent"]] = relationship(back_populates="rule", passive_deletes=True)


class AlertEvent(Base, UUIDPKMixin):
    __tablename__ = "alert_events"

    alert_rule_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("alert_rules.id", ondelete="CASCADE"), nullable=False, index=True
    )
    server_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("servers.id", ondelete="CASCADE"), index=True
    )
    triggered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    value: Mapped[float | None] = mapped_column(Float)
    status: Mapped[AlertEventStatus] = mapped_column(
        Enum(AlertEventStatus, name="alert_event_status"), default=AlertEventStatus.open, nullable=False
    )
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    acknowledged_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )

    rule: Mapped["AlertRule"] = relationship(back_populates="events")
    acknowledged_by: Mapped["User | None"] = relationship()


class MaintenanceWindow(Base, UUIDPKMixin, TimestampMixin):
    """A planned window during which notify_incident() (see app.services.incident_notifier)
    silences in-app/email notifications for the affected server(s) — AlertEvent rows are
    still created normally by metric_thresholds so the history stays accurate, only the
    notification is suppressed. status is never persisted; it's derived from
    starts_at/ends_at/cancelled_at at read time (see app.services.maintenance_windows) so no
    background job is needed to flip it."""

    __tablename__ = "maintenance_windows"

    scope_type: Mapped[MaintenanceScope] = mapped_column(Enum(MaintenanceScope, name="maintenance_scope"), nullable=False)
    scope_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    reason: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_by_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))

    created_by: Mapped["User | None"] = relationship()


class SyntheticCheckResult(Base, UUIDPKMixin):
    """One HTTP reachability probe of Service.health_check_url from one prober server's
    Agent — see app.services.synthetic_checks. No separate "check config" table: the set
    of active checks is just every Service with health_check_url set, times every Server
    with is_synthetic_probe=True."""

    __tablename__ = "synthetic_check_results"

    service_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("services.id", ondelete="CASCADE"), nullable=False, index=True
    )
    prober_server_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("servers.id", ondelete="SET NULL"), index=True
    )
    success: Mapped[bool] = mapped_column(Boolean, nullable=False)
    status_code: Mapped[int | None] = mapped_column(Integer)
    latency_ms: Mapped[float | None] = mapped_column(Float)
    error_message: Mapped[str | None] = mapped_column(Text)
    checked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)


class NotificationChannel(Base, UUIDPKMixin, TimestampMixin):
    __tablename__ = "notification_channels"

    type: Mapped[NotificationChannelType] = mapped_column(
        Enum(NotificationChannelType, name="notification_channel_type"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    config_encrypted: Mapped[str | None] = mapped_column(Text)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class NotificationLog(Base, UUIDPKMixin):
    __tablename__ = "notification_logs"

    channel_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("notification_channels.id", ondelete="CASCADE"), nullable=False, index=True
    )
    alert_event_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("alert_events.id"))
    sent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[NotificationStatus] = mapped_column(Enum(NotificationStatus, name="notification_status"), nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text)


class InAppNotification(Base, UUIDPKMixin):
    """A notification surfaced in CITI's own UI (bell icon) for a specific user —
    distinct from NotificationLog, which tracks outbound channel sends (email/telegram/etc.)."""

    __tablename__ = "in_app_notifications"

    recipient_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    severity: Mapped[AlertSeverity] = mapped_column(Enum(AlertSeverity, name="alert_severity"), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    entity_type: Mapped[str | None] = mapped_column(String(100))
    entity_id: Mapped[str | None] = mapped_column(String(100))
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )
