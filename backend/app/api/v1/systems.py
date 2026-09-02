import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_permission
from app.core.database import get_db
from app.models.identity import User
from app.models.monitoring import InAppNotification
from app.models.systems import System
from app.schemas.system import RecentIncident, SystemCreate, SystemRead, SystemUpdate
from app.services.audit import diff_changed_fields, log_action

router = APIRouter(prefix="/systems", tags=["systems"], dependencies=[Depends(get_current_user)])


@router.get("", response_model=list[SystemRead])
def list_systems(db: Session = Depends(get_db)) -> list[System]:
    return list(db.scalars(select(System).order_by(System.name)))


@router.get("/recent-incidents", response_model=list[RecentIncident])
def list_recent_incidents(limit: int = 10, db: Session = Depends(get_db)) -> list[RecentIncident]:
    """Feeds the Sistemas dashboard's 'Incidentes recientes' panel — reuses the same
    InAppNotification rows already generated for system/service failures (see
    notify_incident() call sites in services.py/deployments.py/backups.py), deduplicated
    across recipients since one incident fans out to several InAppNotification rows."""
    limit = max(1, min(limit, 50))
    notifications = db.scalars(
        select(InAppNotification)
        .where(InAppNotification.entity_type.in_(["system", "service"]))
        .order_by(InAppNotification.created_at.desc())
        .limit(limit * 5)
    )
    seen: set[tuple] = set()
    incidents: list[RecentIncident] = []
    for n in notifications:
        key = (n.title, n.message, n.created_at)
        if key in seen:
            continue
        seen.add(key)
        incidents.append(
            RecentIncident(id=n.id, severity=n.severity.value, title=n.title, message=n.message, created_at=n.created_at)
        )
        if len(incidents) >= limit:
            break
    return incidents


@router.post("", response_model=SystemRead, status_code=status.HTTP_201_CREATED, dependencies=[Depends(require_permission("systems.manage"))])
def create_system(
    payload: SystemCreate, request: Request, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)
) -> System:
    if db.scalar(select(System).where(System.slug == payload.slug)) is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Ya existe un sistema con ese slug")
    system = System(**payload.model_dump())
    db.add(system)
    db.commit()
    db.refresh(system)
    log_action(
        db, current_user, "system.created", "system", system.id,
        details={"name": system.name, "slug": system.slug}, request=request,
    )
    return system


@router.get("/{system_id}", response_model=SystemRead)
def get_system(system_id: uuid.UUID, db: Session = Depends(get_db)) -> System:
    system = db.get(System, system_id)
    if system is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sistema no encontrado")
    return system


@router.patch("/{system_id}", response_model=SystemRead, dependencies=[Depends(require_permission("systems.manage"))])
def update_system(
    system_id: uuid.UUID,
    payload: SystemUpdate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> System:
    system = db.get(System, system_id)
    if system is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sistema no encontrado")
    data = payload.model_dump(exclude_unset=True)
    changes = diff_changed_fields(system, data)
    for field, value in data.items():
        setattr(system, field, value)
    db.commit()
    db.refresh(system)
    log_action(
        db, current_user, "system.updated", "system", system.id,
        details={"changes": changes} if changes else None, request=request,
    )
    return system


@router.delete("/{system_id}", status_code=status.HTTP_204_NO_CONTENT, dependencies=[Depends(require_permission("systems.manage"))])
def delete_system(
    system_id: uuid.UUID, request: Request, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)
) -> None:
    system = db.get(System, system_id)
    if system is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sistema no encontrado")
    deleted_name = system.name
    db.delete(system)
    db.commit()
    log_action(db, current_user, "system.deleted", "system", system_id, details={"name": deleted_name}, request=request)
