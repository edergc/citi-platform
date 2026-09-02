import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models.versions import DeploymentSource, DeploymentStatus


class DeployCheckResponse(BaseModel):
    is_dirty: bool
    dirty_files: list[str]
    current_commit: str | None
    remote_commit: str | None
    commits_behind: int
    error: str | None = None


class DeploymentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    system_id: uuid.UUID
    version_id: uuid.UUID | None
    source: DeploymentSource
    status: DeploymentStatus
    triggered_by_id: uuid.UUID | None
    started_at: datetime | None
    finished_at: datetime | None
    log_output: str | None
    rollback_of_id: uuid.UUID | None
