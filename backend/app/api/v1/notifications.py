import asyncio
import json
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_permission
from app.core.database import get_db
from app.core.security import decrypt_secret, encrypt_secret
from app.models.identity import User
from app.models.monitoring import NotificationChannel, NotificationLog, NotificationStatus
from app.schemas.notification import (
    NotificationChannelCreate,
    NotificationChannelRead,
    NotificationChannelUpdate,
    NotificationLogPage,
    NotificationLogRead,
    NotificationTestRequest,
)
from app.services.audit import diff_changed_fields, log_action
from app.services.notification_senders import SENDERS
from app.services.weekly_report import send_weekly_report

router = APIRouter(prefix="/notification-channels", tags=["notifications"], dependencies=[Depends(get_current_user)])


def _get_config(channel: NotificationChannel) -> dict:
    if not channel.config_encrypted:
        return {}
    return json.loads(decrypt_secret(channel.config_encrypted))


@router.get("", response_model=list[NotificationChannelRead])
def list_channels(db: Session = Depends(get_db)) -> list[NotificationChannel]:
    return list(db.scalars(select(NotificationChannel).order_by(NotificationChannel.name)))


@router.post("", response_model=NotificationChannelRead, status_code=status.HTTP_201_CREATED, dependencies=[Depends(require_permission("notifications.manage"))])
def create_channel(
    payload: NotificationChannelCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> NotificationChannel:
    channel = NotificationChannel(
        type=payload.type,
        name=payload.name,
        enabled=payload.enabled,
        config_encrypted=encrypt_secret(json.dumps(payload.config)),
    )
    db.add(channel)
    db.commit()
    db.refresh(channel)
    log_action(
        db, current_user, "notification_channel.created", "notification_channel", channel.id,
        details={"name": channel.name, "type": channel.type.value}, request=request,
    )
    return channel


@router.patch("/{channel_id}", response_model=NotificationChannelRead, dependencies=[Depends(require_permission("notifications.manage"))])
def update_channel(
    channel_id: uuid.UUID,
    payload: NotificationChannelUpdate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> NotificationChannel:
    channel = db.get(NotificationChannel, channel_id)
    if channel is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Canal no encontrado")
    changes = diff_changed_fields(
        channel,
        {k: v for k, v in {"name": payload.name, "enabled": payload.enabled}.items() if v is not None},
    )
    if payload.name is not None:
        channel.name = payload.name
    if payload.enabled is not None:
        channel.enabled = payload.enabled
    if payload.config is not None:
        channel.config_encrypted = encrypt_secret(json.dumps(payload.config))
        changes["config"] = {"antes": "(configuración anterior no expuesta)", "despues": "(configuración actualizada)"}
    db.commit()
    db.refresh(channel)
    log_action(
        db, current_user, "notification_channel.updated", "notification_channel", channel.id,
        details={"changes": changes} if changes else None, request=request,
    )
    return channel


@router.delete("/{channel_id}", status_code=status.HTTP_204_NO_CONTENT, dependencies=[Depends(require_permission("notifications.manage"))])
def delete_channel(
    channel_id: uuid.UUID, request: Request, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)
) -> None:
    channel = db.get(NotificationChannel, channel_id)
    if channel is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Canal no encontrado")
    deleted_name = channel.name
    db.delete(channel)
    db.commit()
    log_action(
        db, current_user, "notification_channel.deleted", "notification_channel", channel_id,
        details={"name": deleted_name}, request=request,
    )


@router.post("/{channel_id}/test", response_model=NotificationLogRead, dependencies=[Depends(require_permission("notifications.manage"))])
async def test_channel(
    channel_id: uuid.UUID,
    payload: NotificationTestRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> NotificationLog:
    channel = db.get(NotificationChannel, channel_id)
    if channel is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Canal no encontrado")

    sender = SENDERS.get(channel.type.value)
    config = _get_config(channel)

    success, error = await asyncio.to_thread(sender, config, payload.to, payload.message)

    log = NotificationLog(
        channel_id=channel.id,
        sent_at=datetime.now(timezone.utc),
        status=NotificationStatus.sent if success else NotificationStatus.failed,
        error_message=error,
    )
    db.add(log)
    db.commit()
    db.refresh(log)
    log_action(
        db, current_user, "notification_channel.test_sent", "notification_channel", channel_id,
        details={"to": payload.to, "success": success}, request=request,
    )
    return log


@router.post("/weekly-report/trigger", status_code=status.HTTP_202_ACCEPTED, dependencies=[Depends(require_permission("notifications.manage"))])
async def trigger_weekly_report(
    request: Request, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)
) -> dict:
    """Manual send, so the weekly rollup can be verified end-to-end without waiting for
    the real Monday-08:00-Lima schedule in app.main's _weekly_report_loop."""
    await send_weekly_report(db)
    log_action(db, current_user, "notification_channel.weekly_report_triggered", "notification_channel", request=request)
    return {"status": "sent"}


@router.get("/{channel_id}/logs", response_model=NotificationLogPage)
def list_logs(
    channel_id: uuid.UUID,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
) -> NotificationLogPage:
    base_query = select(NotificationLog).where(NotificationLog.channel_id == channel_id)
    total = db.scalar(select(func.count()).select_from(base_query.subquery())) or 0
    items = list(
        db.scalars(base_query.order_by(NotificationLog.sent_at.desc()).offset(offset).limit(limit))
    )
    return NotificationLogPage(items=items, total=total)
