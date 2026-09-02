import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import require_permission
from app.core.database import get_db
from app.models.identity import AuditLog, User
from app.schemas.audit import AuditLogRead

router = APIRouter(prefix="/audit-logs", tags=["audit"], dependencies=[Depends(require_permission("audit.view"))])


@router.get("", response_model=list[AuditLogRead])
def list_audit_logs(
    entity_type: str | None = None,
    action: str | None = None,
    user_id: uuid.UUID | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
) -> list[AuditLogRead]:
    query = select(AuditLog).order_by(AuditLog.created_at.desc())
    if entity_type is not None:
        query = query.where(AuditLog.entity_type == entity_type)
    if action is not None:
        query = query.where(AuditLog.action == action)
    if user_id is not None:
        query = query.where(AuditLog.user_id == user_id)
    if date_from is not None:
        query = query.where(AuditLog.created_at >= date_from)
    if date_to is not None:
        query = query.where(AuditLog.created_at <= date_to)
    query = query.offset(offset).limit(limit)

    logs = list(db.scalars(query))

    user_ids = {log.user_id for log in logs if log.user_id is not None}
    names = {}
    if user_ids:
        names = {u.id: u.full_name for u in db.scalars(select(User).where(User.id.in_(user_ids)))}

    return [
        AuditLogRead(
            id=log.id,
            user_id=log.user_id,
            user_full_name=names.get(log.user_id),
            action=log.action,
            entity_type=log.entity_type,
            entity_id=log.entity_id,
            details=log.details,
            ip_address=str(log.ip_address) if log.ip_address else None,
            created_at=log.created_at,
        )
        for log in logs
    ]


@router.get("/actions", response_model=list[str])
def list_distinct_actions(db: Session = Depends(get_db)) -> list[str]:
    return list(db.scalars(select(AuditLog.action).distinct().order_by(AuditLog.action)))


@router.get("/entity-types", response_model=list[str])
def list_distinct_entity_types(db: Session = Depends(get_db)) -> list[str]:
    return list(db.scalars(select(AuditLog.entity_type).distinct().order_by(AuditLog.entity_type)))
