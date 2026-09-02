import enum
import uuid
from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, Enum, ForeignKey, Numeric, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDPKMixin


class DocumentType(str, enum.Enum):
    manual_tecnico = "manual_tecnico"
    manual_usuario = "manual_usuario"
    arquitectura = "arquitectura"
    diagrama = "diagrama"
    script = "script"
    pdf = "pdf"
    imagen = "imagen"
    video = "video"
    procedimiento = "procedimiento"


class DependencyType(str, enum.Enum):
    library = "library"
    service = "service"
    external_api = "external_api"


class Document(Base, UUIDPKMixin):
    __tablename__ = "documents"

    system_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("systems.id", ondelete="CASCADE"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    doc_type: Mapped[DocumentType] = mapped_column(Enum(DocumentType, name="document_type"), nullable=False)
    file_path: Mapped[str] = mapped_column(String(500), nullable=False)
    version: Mapped[str | None] = mapped_column(String(50))
    uploaded_by_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class License(Base, UUIDPKMixin, TimestampMixin):
    __tablename__ = "licenses"

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    vendor: Mapped[str | None] = mapped_column(String(255))
    system_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("systems.id"), index=True)
    server_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("servers.id"), index=True)
    expiry_date: Mapped[date | None] = mapped_column(Date, index=True)
    seats: Mapped[int | None] = mapped_column()
    cost: Mapped[float | None] = mapped_column(Numeric(12, 2))
    notes: Mapped[str | None] = mapped_column(Text)


class Dependency(Base, UUIDPKMixin, TimestampMixin):
    __tablename__ = "dependencies"

    system_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("systems.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    type: Mapped[DependencyType] = mapped_column(Enum(DependencyType, name="dependency_type"), nullable=False)
    version: Mapped[str | None] = mapped_column(String(100))
    criticality: Mapped[str | None] = mapped_column(String(20))
    notes: Mapped[str | None] = mapped_column(Text)


class CronJob(Base, UUIDPKMixin, TimestampMixin):
    __tablename__ = "cron_jobs"

    service_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("services.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    schedule: Mapped[str] = mapped_column(String(100), nullable=False)
    command: Mapped[str] = mapped_column(Text, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_status: Mapped[str | None] = mapped_column(String(20))
