import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models.systems import SystemCriticality, SystemStatus


class SystemRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    slug: str
    description: str | None
    category: str | None
    criticality: SystemCriticality
    status: SystemStatus
    owner_user_id: uuid.UUID | None
    repo_url: str | None
    default_branch: str | None
    repo_local_path: str | None
    deploy_build_command: str | None
    created_at: datetime
    updated_at: datetime


class SystemCreate(BaseModel):
    name: str
    slug: str
    description: str | None = None
    category: str | None = None
    criticality: SystemCriticality = SystemCriticality.medium
    owner_user_id: uuid.UUID | None = None
    repo_url: str | None = None
    default_branch: str | None = "main"


class SystemUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    category: str | None = None
    criticality: SystemCriticality | None = None
    status: SystemStatus | None = None
    owner_user_id: uuid.UUID | None = None
    repo_url: str | None = None
    default_branch: str | None = None
    repo_local_path: str | None = None
    deploy_build_command: str | None = None


class RecentIncident(BaseModel):
    id: uuid.UUID
    severity: str
    title: str
    message: str
    created_at: datetime
