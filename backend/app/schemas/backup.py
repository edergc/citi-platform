import uuid
from datetime import datetime

from croniter import croniter
from pydantic import BaseModel, ConfigDict, field_validator

from app.models.backups import BackupType, RunStatus, TriggerType


def _validate_schedule_cron(value: str | None) -> str | None:
    if value is not None and not croniter.is_valid(value):
        raise ValueError("schedule_cron no es una expresión cron válida (formato: minuto hora día mes día-semana)")
    return value


class BackupJobCreate(BaseModel):
    service_id: uuid.UUID
    type: BackupType
    source_path: str
    storage_path: str
    retention_days: int = 30
    schedule_cron: str | None = None

    _validate_schedule_cron = field_validator("schedule_cron")(_validate_schedule_cron)


class BackupJobUpdate(BaseModel):
    storage_path: str | None = None
    retention_days: int | None = None
    enabled: bool | None = None
    schedule_cron: str | None = None

    _validate_schedule_cron = field_validator("schedule_cron")(_validate_schedule_cron)


class BackupJobRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    service_id: uuid.UUID
    type: BackupType
    source_path: str
    storage_path: str
    retention_days: int
    schedule_cron: str | None
    enabled: bool
    created_at: datetime


class BackupRunRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    backup_job_id: uuid.UUID
    status: RunStatus
    triggered_by: TriggerType
    size_bytes: int | None
    sha256_hash: str | None
    storage_path: str | None
    started_at: datetime | None
    finished_at: datetime | None
    error_message: str | None


class BackupRunPage(BaseModel):
    items: list[BackupRunRead]
    total: int


class RestoreOperationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    backup_run_id: uuid.UUID
    status: RunStatus
    restored_to_path: str | None
    started_at: datetime | None
    finished_at: datetime | None
    notes: str | None
