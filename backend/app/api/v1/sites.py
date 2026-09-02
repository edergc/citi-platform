import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_permission
from app.core.database import get_db
from app.models.identity import User, UserSite
from app.models.infrastructure import Server, Site
from app.schemas.server import SiteUserBrief
from app.schemas.site import SiteCreate, SiteRead, SiteUpdate
from app.services.audit import diff_changed_fields, log_action

router = APIRouter(prefix="/sites", tags=["sites"], dependencies=[Depends(get_current_user)])

_manage = Depends(require_permission("sites.manage"))


@router.get("", response_model=list[SiteRead])
def list_sites(db: Session = Depends(get_db)) -> list[Site]:
    return list(db.scalars(select(Site).order_by(Site.name)))


@router.get("/{site_id}/users", response_model=list[SiteUserBrief])
def list_site_users(site_id: uuid.UUID, db: Session = Depends(get_db)) -> list[User]:
    """Deliberately lighter than the users.manage-gated /users endpoint (id + name only,
    no DNI/email) — needed so a técnico without users.manage can still pick a colleague
    at their own sede as a server's responsable."""
    site = db.get(Site, site_id)
    if site is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sede no encontrada")
    return list(
        db.scalars(
            select(User)
            .join(UserSite, UserSite.user_id == User.id)
            .where(UserSite.site_id == site_id, User.is_active.is_(True))
            .order_by(User.full_name)
        )
    )


@router.post("", response_model=SiteRead, status_code=status.HTTP_201_CREATED, dependencies=[_manage])
def create_site(
    payload: SiteCreate, request: Request, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)
) -> Site:
    site = Site(**payload.model_dump())
    db.add(site)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Ya existe una sede con ese código") from exc
    db.refresh(site)
    log_action(db, current_user, "site.created", "site", site.id, details={"name": site.name, "code": site.code}, request=request)
    return site


@router.patch("/{site_id}", response_model=SiteRead, dependencies=[_manage])
def update_site(
    site_id: uuid.UUID,
    payload: SiteUpdate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Site:
    site = db.get(Site, site_id)
    if site is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sede no encontrada")
    data = payload.model_dump(exclude_unset=True)
    changes = diff_changed_fields(site, data)
    for field, value in data.items():
        setattr(site, field, value)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Ya existe una sede con ese código") from exc
    db.refresh(site)
    log_action(
        db, current_user, "site.updated", "site", site.id, details={"changes": changes} if changes else None, request=request
    )
    return site


@router.delete("/{site_id}", status_code=status.HTTP_204_NO_CONTENT, dependencies=[_manage])
def delete_site(
    site_id: uuid.UUID, request: Request, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)
) -> None:
    site = db.get(Site, site_id)
    if site is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sede no encontrada")

    has_servers = db.scalar(select(Server.id).where(Server.site_id == site_id).limit(1)) is not None
    has_users = db.scalar(select(UserSite.user_id).where(UserSite.site_id == site_id).limit(1)) is not None
    if has_servers or has_users:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="No se puede eliminar: hay servidores o usuarios asignados a esta sede. Reasígnalos primero.",
        )

    deleted_name = site.name
    db.delete(site)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="No se puede eliminar: hay servidores o usuarios asignados a esta sede",
        ) from exc
    log_action(db, current_user, "site.deleted", "site", site_id, details={"name": deleted_name}, request=request)
