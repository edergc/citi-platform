import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models.backups import BackupType, RunStatus, TriggerType


class BackupJobCreate(BaseModel):
    service_id: uuid.UUID
    type: BackupType
    source_path: str
    storage_path: str
    retention_days: int = 30


class BackupJobUpdate(BaseModel):
    storage_path: str | None = None
    retention_days: int | None = None
    enabled: bool | None = None


class BackupJobRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    service_id: uuid.UUID
    type: BackupType
    source_path: str
    storage_path: str
    retention_days: int
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
