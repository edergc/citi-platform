import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_permission
from app.core.database import get_db
from app.core.security import encrypt_secret
from app.models.config import ConfigEntry, ConfigEntryHistory, Environment
from app.models.identity import User
from app.schemas.config import ConfigEntryCreate, ConfigEntryHistoryRead, ConfigEntryRead
from app.services.audit import SENSITIVE_VALUE_MASK, log_action

router = APIRouter(prefix="/config-entries", tags=["config"], dependencies=[Depends(get_current_user)])

MASKED_VALUE = "••••••••"


def _get_or_create_environment(db: Session, code: str) -> Environment:
    env = db.scalar(select(Environment).where(Environment.code == code))
    if env is None:
        env = Environment(code=code, name=code.capitalize())
        db.add(env)
        db.commit()
        db.refresh(env)
    return env


def _mask(entry: ConfigEntry) -> ConfigEntryRead:
    read = ConfigEntryRead.model_validate(entry)
    if entry.is_secret and entry.value:
        read.value = MASKED_VALUE
    return read


@router.post("", response_model=ConfigEntryRead, status_code=status.HTTP_201_CREATED, dependencies=[Depends(require_permission("config.manage"))])
def upsert_config_entry(
    payload: ConfigEntryCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ConfigEntryRead:
    environment = _get_or_create_environment(db, payload.environment_code)
    stored_value = encrypt_secret(payload.value) if payload.is_secret else payload.value

    entry = db.scalar(
        select(ConfigEntry).where(
            ConfigEntry.service_id == payload.service_id,
            ConfigEntry.environment_id == environment.id,
            ConfigEntry.key == payload.key,
        )
    )
    was_created = entry is None
    changes: dict[str, dict[str, object]] = {}
    if entry is None:
        entry = ConfigEntry(
            service_id=payload.service_id,
            environment_id=environment.id,
            key=payload.key,
            value=stored_value,
            is_secret=payload.is_secret,
            description=payload.description,
            version=1,
            updated_by_id=current_user.id,
        )
        db.add(entry)
    else:
        db.add(
            ConfigEntryHistory(
                config_entry_id=entry.id,
                previous_value=entry.value,
                changed_by_id=current_user.id,
                changed_at=datetime.now(timezone.utc),
            )
        )
        # Secretos: nunca se registra el valor real en la auditoría, solo que cambió.
        was_secret = entry.is_secret
        if entry.value != stored_value:
            changes["value"] = (
                {"antes": SENSITIVE_VALUE_MASK, "despues": SENSITIVE_VALUE_MASK}
                if (was_secret or payload.is_secret)
                else {"antes": entry.value, "despues": payload.value}
            )
        if entry.description != payload.description:
            changes["description"] = {"antes": entry.description, "despues": payload.description}
        if entry.is_secret != payload.is_secret:
            changes["is_secret"] = {"antes": entry.is_secret, "despues": payload.is_secret}

        entry.value = stored_value
        entry.is_secret = payload.is_secret
        entry.description = payload.description
        entry.version += 1
        entry.updated_by_id = current_user.id

    db.commit()
    db.refresh(entry)
    log_action(
        db,
        current_user,
        "config.created" if was_created else "config.updated",
        "config_entry",
        entry.id,
        details=(
            {
                "service_id": str(payload.service_id),
                "key": payload.key,
                "is_secret": payload.is_secret,
                "value": MASKED_VALUE if payload.is_secret else payload.value,
            }
            if was_created
            else {"key": payload.key, "changes": changes}
        ),
        request=request,
    )
    return _mask(entry)


@router.get("", response_model=list[ConfigEntryRead])
def list_config_entries(service_id: uuid.UUID, db: Session = Depends(get_db)) -> list[ConfigEntryRead]:
    entries = db.scalars(select(ConfigEntry).where(ConfigEntry.service_id == service_id))
    return [_mask(e) for e in entries]


@router.get("/{entry_id}/history", response_model=list[ConfigEntryHistoryRead], dependencies=[Depends(require_permission("config.manage"))])
def get_config_entry_history(entry_id: uuid.UUID, db: Session = Depends(get_db)) -> list[ConfigEntryHistoryRead]:
    entry = db.get(ConfigEntry, entry_id)
    if entry is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Config entry no encontrada")
    history = db.scalars(
        select(ConfigEntryHistory)
        .where(ConfigEntryHistory.config_entry_id == entry_id)
        .order_by(ConfigEntryHistory.changed_at.desc())
    )
    results = []
    for h in history:
        value = MASKED_VALUE if entry.is_secret and h.previous_value else h.previous_value
        results.append(ConfigEntryHistoryRead(id=h.id, previous_value=value, changed_at=h.changed_at))
    return results


@router.delete("/{entry_id}", status_code=status.HTTP_204_NO_CONTENT, dependencies=[Depends(require_permission("config.manage"))])
def delete_config_entry(
    entry_id: uuid.UUID, request: Request, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)
) -> None:
    entry = db.get(ConfigEntry, entry_id)
    if entry is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Config entry no encontrada")
    deleted_key = entry.key
    db.delete(entry)
    db.commit()
    log_action(
        db, current_user, "config.deleted", "config_entry", entry_id, details={"key": deleted_key}, request=request
    )
