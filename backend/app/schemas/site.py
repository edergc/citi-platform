import uuid

from pydantic import BaseModel, ConfigDict


class SiteRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    code: str
    address: str | None
    timezone: str


class SiteCreate(BaseModel):
    name: str
    code: str
    address: str | None = None
    timezone: str = "America/Lima"


class SiteUpdate(BaseModel):
    name: str | None = None
    code: str | None = None
    address: str | None = None
    timezone: str | None = None
