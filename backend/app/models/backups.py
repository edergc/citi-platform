import enum
import uuid
from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, Enum, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPKMixin


class BackupType(str, enum.Enum):
    database = "database"
    files = "files"
    full = "full"


class RunStatus(str, enum.Enum):
    pending = "pending"
    running = "running"
    success = "success"
    failed = "failed"


class TriggerType(str, enum.Enum):
    manual = "manual"
    scheduled = "scheduled"


class BackupJob(Base, UUIDPKMixin, TimestampMixin):
    __tablename__ = "backup_jobs"

    service_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("services.id", ondelete="CASCADE"), nullable=False, index=True
    )
    type: Mapped[BackupType] = mapped_column(Enum(BackupType, name="backup_type"), nullable=False)
    source_path: Mapped[str] = mapped_column(String(500), nullable=False)
    schedule_cron: Mapped[str | None] = mapped_column(String(100))
    retention_days: Mapped[int] = mapped_column(Integer, default=30, nullable=False)
    storage_path: Mapped[str] = mapped_column(String(500), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_by_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))

    runs: Mapped[list["BackupRun"]] = relationship(back_populates="job")


class BackupRun(Base, UUIDPKMixin):
    __tablename__ = "backup_runs"

    backup_job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("backup_jobs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    status: Mapped[RunStatus] = mapped_column(Enum(RunStatus, name="run_status"), default=RunStatus.pending, nullable=False)
    triggered_by: Mapped[TriggerType] = mapped_column(Enum(TriggerType, name="trigger_type"), nullable=False)
    size_bytes: Mapped[int | None] = mapped_column(BigInteger)
    sha256_hash: Mapped[str | None] = mapped_column(String(64))
    storage_path: Mapped[str | None] = mapped_column(String(500))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_message: Mapped[str | None] = mapped_column(Text)
    purged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    job: Mapped["BackupJob"] = relationship(back_populates="runs")


class RestoreOperation(Base, UUIDPKMixin):
    __tablename__ = "restore_operations"

    backup_run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("backup_runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    requested_by_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))
    target_service_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("services.id"))
    status: Mapped[RunStatus] = mapped_column(Enum(RunStatus, name="run_status"), default=RunStatus.pending, nullable=False)
    restored_to_path: Mapped[str | None] = mapped_column(String(500))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    notes: Mapped[str | None] = mapped_column(Text)
