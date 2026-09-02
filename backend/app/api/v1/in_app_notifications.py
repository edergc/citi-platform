import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models.identity import User
from app.models.monitoring import InAppNotification
from app.schemas.in_app_notification import InAppNotificationRead, UnreadCountResponse

router = APIRouter(prefix="/in-app-notifications", tags=["in-app-notifications"], dependencies=[Depends(get_current_user)])


@router.get("", response_model=list[InAppNotificationRead])
def list_my_notifications(
    unread_only: bool = False,
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[InAppNotification]:
    query = select(InAppNotification).where(InAppNotification.recipient_id == current_user.id)
    if unread_only:
        query = query.where(InAppNotification.read_at.is_(None))
    query = query.order_by(InAppNotification.created_at.desc()).limit(limit)
    return list(db.scalars(query))


@router.get("/unread-count", response_model=UnreadCountResponse)
def unread_count(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)) -> UnreadCountResponse:
    count = db.scalar(
        select(func.count())
        .select_from(InAppNotification)
        .where(InAppNotification.recipient_id == current_user.id, InAppNotification.read_at.is_(None))
    )
    return UnreadCountResponse(count=count or 0)


@router.post("/{notification_id}/read", response_model=InAppNotificationRead)
def mark_read(
    notification_id: uuid.UUID, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)
) -> InAppNotification:
    notification = db.get(InAppNotification, notification_id)
    if notification is None or notification.recipient_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Notificación no encontrada")
    if notification.read_at is None:
        notification.read_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(notification)
    return notification


@router.post("/read-all", status_code=status.HTTP_204_NO_CONTENT)
def mark_all_read(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)) -> None:
    now = datetime.now(timezone.utc)
    db.execute(
        InAppNotification.__table__.update()
        .where(InAppNotification.recipient_id == current_user.id, InAppNotification.read_at.is_(None))
        .values(read_at=now)
    )
    db.commit()
