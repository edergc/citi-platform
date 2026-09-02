import uuid
from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPKMixin


class Environment(Base, UUIDPKMixin):
    """Lookup table: dev / qa / prod."""

    __tablename__ = "environments"

    code: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(50), nullable=False)


class ConfigEntry(Base, UUIDPKMixin, TimestampMixin):
    """Current value of a config key. Secret values are stored Fernet-encrypted (see core.security)."""

    __tablename__ = "config_entries"
    __table_args__ = (UniqueConstraint("service_id", "environment_id", "key", name="uq_config_entry_key"),)

    service_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("services.id", ondelete="CASCADE"), nullable=False, index=True
    )
    environment_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("environments.id"), nullable=False, index=True
    )
    key: Mapped[str] = mapped_column(String(255), nullable=False)
    value: Mapped[str | None] = mapped_column(Text)
    is_secret: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    updated_by_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))

    history: Mapped[list["ConfigEntryHistory"]] = relationship(back_populates="config_entry")


class ConfigEntryHistory(Base, UUIDPKMixin):
    __tablename__ = "config_entry_history"

    config_entry_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("config_entries.id", ondelete="CASCADE"), nullable=False, index=True
    )
    previous_value: Mapped[str | None] = mapped_column(Text)
    changed_by_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))
    changed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    change_reason: Mapped[str | None] = mapped_column(Text)

    config_entry: Mapped["ConfigEntry"] = relationship(back_populates="history")


class Certificate(Base, UUIDPKMixin, TimestampMixin):
    __tablename__ = "certificates"

    domain: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    server_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("servers.id"), index=True)
    service_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("services.id"), index=True)
    issuer: Mapped[str | None] = mapped_column(String(255))
    valid_from: Mapped[date | None] = mapped_column(Date)
    valid_to: Mapped[date | None] = mapped_column(Date, index=True)
    auto_renew: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
