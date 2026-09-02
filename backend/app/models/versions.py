import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPKMixin


class VersionStatus(str, enum.Enum):
    active = "active"
    rolled_back = "rolled_back"
    deprecated = "deprecated"


class DeploymentSource(str, enum.Enum):
    git = "git"
    zip = "zip"
    manual = "manual"


class DeploymentStatus(str, enum.Enum):
    pending = "pending"
    running = "running"
    success = "success"
    failed = "failed"
    rolled_back = "rolled_back"


class SystemVersion(Base, UUIDPKMixin, TimestampMixin):
    __tablename__ = "system_versions"

    system_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("systems.id", ondelete="CASCADE"), nullable=False, index=True
    )
    version_number: Mapped[str] = mapped_column(String(50), nullable=False)
    git_commit_hash: Mapped[str | None] = mapped_column(String(40))
    git_branch: Mapped[str | None] = mapped_column(String(100))
    release_notes: Mapped[str | None] = mapped_column(Text)
    status: Mapped[VersionStatus] = mapped_column(
        Enum(VersionStatus, name="version_status"), default=VersionStatus.active, nullable=False
    )
    released_by_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))
    released_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    deployments: Mapped[list["Deployment"]] = relationship(back_populates="version")


class Deployment(Base, UUIDPKMixin):
    __tablename__ = "deployments"

    system_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("systems.id", ondelete="CASCADE"), nullable=False, index=True
    )
    version_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("system_versions.id"))
    source: Mapped[DeploymentSource] = mapped_column(Enum(DeploymentSource, name="deployment_source"), nullable=False)
    status: Mapped[DeploymentStatus] = mapped_column(
        Enum(DeploymentStatus, name="deployment_status"), default=DeploymentStatus.pending, nullable=False
    )
    triggered_by_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    log_output: Mapped[str | None] = mapped_column(Text)
    rollback_of_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("deployments.id"))

    version: Mapped["SystemVersion | None"] = relationship(back_populates="deployments")
