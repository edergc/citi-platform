import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models.versions import VersionStatus


class SystemVersionCreate(BaseModel):
    version_number: str
    git_commit_hash: str | None = None
    git_branch: str | None = None
    release_notes: str | None = None


class SystemVersionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    system_id: uuid.UUID
    version_number: str
    git_commit_hash: str | None
    git_branch: str | None
    release_notes: str | None
    status: VersionStatus
    released_by_id: uuid.UUID | None
    released_at: datetime | None
    created_at: datetime
