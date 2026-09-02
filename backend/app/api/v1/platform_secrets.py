from fastapi import APIRouter, Depends, Request, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_permission
from app.core.database import get_db
from app.core.security import decrypt_secret, encrypt_secret
from app.models.identity import User
from app.models.platform_secret import PlatformSecret
from app.services.audit import log_action

router = APIRouter(
    prefix="/platform-secrets",
    tags=["platform-secrets"],
    dependencies=[Depends(require_permission("platform_secrets.manage"))],
)


class PlatformSecretSet(BaseModel):
    value: str
    description: str | None = None


class PlatformSecretStatus(BaseModel):
    key: str
    is_set: bool
    description: str | None


def get_platform_secret(db: Session, key: str) -> str | None:
    secret = db.scalar(select(PlatformSecret).where(PlatformSecret.key == key))
    if secret is None:
        return None
    return decrypt_secret(secret.value_encrypted)


@router.put("/{key}", response_model=PlatformSecretStatus, status_code=status.HTTP_200_OK)
def set_platform_secret(
    key: str,
    payload: PlatformSecretSet,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> PlatformSecretStatus:
    secret = db.scalar(select(PlatformSecret).where(PlatformSecret.key == key))
    encrypted = encrypt_secret(payload.value)
    was_created = secret is None
    if secret is None:
        secret = PlatformSecret(key=key, value_encrypted=encrypted, description=payload.description)
        db.add(secret)
        value_changed = True
        old_description = None
    else:
        old_description = secret.description
        value_changed = decrypt_secret(secret.value_encrypted) != payload.value
        secret.value_encrypted = encrypted
        secret.description = payload.description
    db.commit()
    details: dict[str, object] = {"key": key, "value_changed": True if was_created else value_changed}
    if not was_created and old_description != payload.description:
        details["description"] = {"antes": old_description, "despues": payload.description}
    log_action(db, current_user, "platform_secret.updated", "platform_secret", key, details=details, request=request)
    return PlatformSecretStatus(key=key, is_set=True, description=secret.description)


@router.get("/{key}", response_model=PlatformSecretStatus)
def get_platform_secret_status(key: str, db: Session = Depends(get_db)) -> PlatformSecretStatus:
    secret = db.scalar(select(PlatformSecret).where(PlatformSecret.key == key))
    return PlatformSecretStatus(key=key, is_set=secret is not None, description=secret.description if secret else None)
