import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models.infrastructure import AgentStatus


class EnrollTokenResponse(BaseModel):
    server_id: uuid.UUID
    token: str


class AgentEnrollRequest(BaseModel):
    server_id: uuid.UUID
    token: str


class AgentEnrollResponse(BaseModel):
    agent_id: uuid.UUID
    agent_token: str


class AgentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    server_id: uuid.UUID
    version: str | None
    status: AgentStatus
    last_heartbeat_at: datetime | None
    enrolled_at: datetime | None
