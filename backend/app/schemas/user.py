import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    dni: str
    email: EmailStr | None = None
    username: str
    full_name: str
    phone: str | None = None
    site_ids: list[uuid.UUID] = []
    site_names: list[str] = []
    role_id: uuid.UUID | None = None
    role_name: str | None = None
    permission_codes: list[str] = []
    is_active: bool
    is_superuser: bool
    mfa_enabled: bool
    last_login_at: datetime | None
    created_at: datetime


class UserCreate(BaseModel):
    dni: str
    email: EmailStr | None = None
    username: str
    full_name: str
    password: str
    phone: str | None = None
    site_ids: list[uuid.UUID] = []
    role_id: uuid.UUID | None = None
    is_superuser: bool = False
    is_active: bool = True


class UserUpdate(BaseModel):
    email: EmailStr | None = None
    username: str | None = None
    full_name: str | None = None
    phone: str | None = None
    site_ids: list[uuid.UUID] | None = None
    role_id: uuid.UUID | None = None
    is_active: bool | None = None
    is_superuser: bool | None = None


class UserSetPassword(BaseModel):
    new_password: str
