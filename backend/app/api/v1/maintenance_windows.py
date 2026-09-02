import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_visible_site_ids, require_permission
from app.core.database import get_db
from app.models.identity import User
from app.models.monitoring import MaintenanceScope, MaintenanceWindow
from app.schemas.maintenance_window import MaintenanceWindowCreate, MaintenanceWindowRead, MaintenanceWindowUpdate
from app.services.audit import diff_changed_fields, log_action
from app.services.maintenance_windows import MaintenanceStatus, compute_status, resolve_scope as _resolve_scope

router = APIRouter(prefix="/maintenance-windows", tags=["maintenance-windows"], dependencies=[Depends(get_current_user)])


def _ensure_scope_visible(effective_site_id: uuid.UUID | None, site_ids: list[uuid.UUID] | None) -> None:
    if site_ids is not None and (effective_site_id is None or effective_site_id not in site_ids):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ventana de mantenimiento no encontrada")


def _to_read(db: Session, window: MaintenanceWindow) -> MaintenanceWindowRead:
    scope_label, _ = _resolve_scope(db, window.scope_type, window.scope_id)
    return MaintenanceWindowRead(
        id=window.id,
        scope_type=window.scope_type,
        scope_id=window.scope_id,
        scope_label=scope_label,
        reason=window.reason,
        description=window.description,
        starts_at=window.starts_at,
        ends_at=window.ends_at,
        cancelled_at=window.cancelled_at,
        status=compute_status(window),
        created_by_id=window.created_by_id,
        created_by_name=window.created_by.full_name if window.created_by else None,
        created_at=window.created_at,
    )


@router.get("", response_model=list[MaintenanceWindowRead])
def list_maintenance_windows(
    status_filter: MaintenanceStatus | None = None,
    scope_type_filter: MaintenanceScope | None = None,
    limit: int = 100,
    db: Session = Depends(get_db),
    site_ids: list[uuid.UUID] | None = Depends(get_visible_site_ids),
) -> list[MaintenanceWindowRead]:
    limit = max(1, min(limit, 300))
    now = datetime.now(timezone.utc)
    query = select(MaintenanceWindow).order_by(MaintenanceWindow.starts_at.desc())

    if scope_type_filter is not None:
        query = query.where(MaintenanceWindow.scope_type == scope_type_filter)
    if status_filter == "active":
        query = query.where(
            MaintenanceWindow.cancelled_at.is_(None), MaintenanceWindow.starts_at <= now, MaintenanceWindow.ends_at >= now
        )
    elif status_filter == "scheduled":
        query = query.where(MaintenanceWindow.cancelled_at.is_(None), MaintenanceWindow.starts_at > now)
    elif status_filter == "ended":
        query = query.where(MaintenanceWindow.cancelled_at.is_(None), MaintenanceWindow.ends_at < now)
    elif status_filter == "cancelled":
        query = query.where(MaintenanceWindow.cancelled_at.isnot(None))

    results: list[MaintenanceWindowRead] = []
    for window in db.scalars(query):
        _, effective_site_id = _resolve_scope(db, window.scope_type, window.scope_id)
        if site_ids is not None and (effective_site_id is None or effective_site_id not in site_ids):
            continue
        results.append(_to_read(db, window))
        if len(results) >= limit:
            break
    return results


@router.post(
    "", response_model=MaintenanceWindowRead, status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission("servers.manage"))],
)
def create_maintenance_window(
    payload: MaintenanceWindowCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    site_ids: list[uuid.UUID] | None = Depends(get_visible_site_ids),
) -> MaintenanceWindowRead:
    scope_label, effective_site_id = _resolve_scope(db, payload.scope_type, payload.scope_id)
    if effective_site_id is None and payload.scope_type == MaintenanceScope.server:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Servidor no encontrado")
    if scope_label == "sede eliminada":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sede no encontrada")
    _ensure_scope_visible(effective_site_id, site_ids)

    window = MaintenanceWindow(**payload.model_dump(), created_by_id=current_user.id)
    db.add(window)
    db.commit()
    db.refresh(window)
    log_action(
        db, current_user, "maintenance_window.created", "maintenance_window", window.id,
        details={"alcance": f"{payload.scope_type.value}:{scope_label}", "motivo": payload.reason},
        request=request,
    )
    return _to_read(db, window)


@router.patch(
    "/{window_id}", response_model=MaintenanceWindowRead, dependencies=[Depends(require_permission("servers.manage"))]
)
def update_maintenance_window(
    window_id: uuid.UUID,
    payload: MaintenanceWindowUpdate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    site_ids: list[uuid.UUID] | None = Depends(get_visible_site_ids),
) -> MaintenanceWindowRead:
    window = db.get(MaintenanceWindow, window_id)
    if window is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ventana de mantenimiento no encontrada")
    _, effective_site_id = _resolve_scope(db, window.scope_type, window.scope_id)
    _ensure_scope_visible(effective_site_id, site_ids)

    current_status = compute_status(window)
    if current_status in ("ended", "cancelled"):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="No se puede editar una ventana finalizada o cancelada")

    data = payload.model_dump(exclude_unset=True)
    if "ends_at" in data and data["ends_at"] is not None and data["ends_at"] <= window.starts_at:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="ends_at debe ser posterior al inicio de la ventana")
    changes = diff_changed_fields(window, data)
    for field, value in data.items():
        setattr(window, field, value)
    db.commit()
    db.refresh(window)
    log_action(
        db, current_user, "maintenance_window.updated", "maintenance_window", window.id,
        details={"changes": changes} if changes else None, request=request,
    )
    return _to_read(db, window)


@router.post(
    "/{window_id}/cancel", response_model=MaintenanceWindowRead, dependencies=[Depends(require_permission("servers.manage"))]
)
def cancel_maintenance_window(
    window_id: uuid.UUID,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    site_ids: list[uuid.UUID] | None = Depends(get_visible_site_ids),
) -> MaintenanceWindowRead:
    window = db.get(MaintenanceWindow, window_id)
    if window is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ventana de mantenimiento no encontrada")
    _, effective_site_id = _resolve_scope(db, window.scope_type, window.scope_id)
    _ensure_scope_visible(effective_site_id, site_ids)

    current_status = compute_status(window)
    if current_status in ("ended", "cancelled"):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Esta ventana ya terminó o fue cancelada")

    window.cancelled_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(window)
    log_action(
        db, current_user, "maintenance_window.cancelled", "maintenance_window", window.id,
        details={"motivo": window.reason}, request=request,
    )
    return _to_read(db, window)
