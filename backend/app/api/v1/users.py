import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_permission
from app.core.database import get_db
from app.core.security import hash_password
from app.models.identity import Role, User, UserRoleAssignment
from app.models.infrastructure import Site
from app.schemas.user import UserCreate, UserRead, UserSetPassword, UserUpdate
from app.services.audit import diff_changed_fields, log_action
from app.services.user_presentation import global_role_map, to_user_read, user_sites_map

router = APIRouter(prefix="/users", tags=["users"])

_manage = Depends(require_permission("users.manage"))

_UNSET = object()
_site_names = user_sites_map
_global_roles = global_role_map
_to_read = to_user_read


def _set_sites(db: Session, user: User, site_ids: list[uuid.UUID]) -> None:
    user.sites = list(db.scalars(select(Site).where(Site.id.in_(site_ids)))) if site_ids else []


def _set_global_role(db: Session, user: User, role_id: uuid.UUID | None) -> None:
    db.execute(
        delete(UserRoleAssignment).where(
            UserRoleAssignment.user_id == user.id, UserRoleAssignment.scope_system_id.is_(None)
        )
    )
    if role_id is not None:
        role = db.get(Role, role_id)
        if role is None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Perfil no encontrado")
        db.add(UserRoleAssignment(user_id=user.id, role_id=role_id, scope_system_id=None))


@router.get("", response_model=list[UserRead], dependencies=[_manage])
def list_users(db: Session = Depends(get_db)) -> list[UserRead]:
    users = list(db.scalars(select(User).order_by(User.full_name)))
    sites = _site_names(db)
    roles = _global_roles(db)
    return [_to_read(u, sites, roles) for u in users]


@router.post("", response_model=UserRead, status_code=status.HTTP_201_CREATED, dependencies=[_manage])
def create_user(
    payload: UserCreate, request: Request, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)
) -> UserRead:
    user = User(
        dni=payload.dni,
        email=payload.email,
        username=payload.username,
        full_name=payload.full_name,
        phone=payload.phone,
        hashed_password=hash_password(payload.password),
        is_superuser=payload.is_superuser,
        is_active=payload.is_active,
    )
    db.add(user)
    try:
        db.flush()
        _set_global_role(db, user, payload.role_id)
        _set_sites(db, user, payload.site_ids)
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="El DNI, correo o usuario ya está registrado"
        ) from exc
    db.refresh(user)
    log_action(
        db, current_user, "user.created", "user", user.id,
        details={"dni": user.dni, "username": user.username, "is_superuser": user.is_superuser}, request=request,
    )
    return _to_read(user, _site_names(db), _global_roles(db))


@router.patch("/{user_id}", response_model=UserRead, dependencies=[_manage])
def update_user(
    user_id: uuid.UUID,
    payload: UserUpdate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> UserRead:
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Usuario no encontrado")

    data = payload.model_dump(exclude_unset=True)

    if data.get("is_superuser") is False and user.is_superuser and user.id == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="No puedes quitarte tus propios privilegios de administrador"
        )
    if data.get("is_active") is False and user.id == current_user.id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No puedes desactivar tu propia cuenta")

    role_id = data.pop("role_id", _UNSET)
    site_ids = data.pop("site_ids", _UNSET)
    changes = diff_changed_fields(user, data, sensitive_fields=frozenset({"hashed_password"}))

    for field, value in data.items():
        setattr(user, field, value)

    if role_id is not _UNSET:
        old_role_id = db.scalar(
            select(UserRoleAssignment.role_id).where(
                UserRoleAssignment.user_id == user.id, UserRoleAssignment.scope_system_id.is_(None)
            )
        )
        if old_role_id != role_id:
            changes["role_id"] = {"antes": str(old_role_id) if old_role_id else None, "despues": str(role_id) if role_id else None}
        _set_global_role(db, user, role_id)

    if site_ids is not _UNSET:
        old_site_ids = sorted(str(s.id) for s in user.sites)
        new_site_ids = sorted(str(s) for s in site_ids)
        if old_site_ids != new_site_ids:
            changes["site_ids"] = {"antes": old_site_ids, "despues": new_site_ids}
        _set_sites(db, user, site_ids)

    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="El correo o usuario ya está en uso") from exc
    db.refresh(user)
    log_action(
        db, current_user, "user.updated", "user", user.id, details={"changes": changes} if changes else None, request=request
    )
    return _to_read(user, _site_names(db), _global_roles(db))


@router.post("/{user_id}/set-password", status_code=status.HTTP_204_NO_CONTENT, dependencies=[_manage])
def set_user_password(
    user_id: uuid.UUID,
    payload: UserSetPassword,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> None:
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Usuario no encontrado")
    if len(payload.new_password) < 8:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="La contraseña debe tener al menos 8 caracteres")
    user.hashed_password = hash_password(payload.new_password)
    db.commit()
    log_action(
        db, current_user, "user.password_reset_by_admin", "user", user.id,
        details={"usuario_afectado": user.username, "dni_afectado": user.dni}, request=request,
    )


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT, dependencies=[_manage])
def delete_user(
    user_id: uuid.UUID, request: Request, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)
) -> None:
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Usuario no encontrado")
    if user.id == current_user.id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No puedes eliminar tu propia cuenta")
    if user.is_superuser:
        remaining = db.scalar(
            select(func.count()).select_from(User).where(User.is_superuser.is_(True), User.id != user_id)
        )
        if not remaining:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="No puedes eliminar al último administrador del sistema"
            )

    deleted_dni, deleted_username = user.dni, user.username
    db.delete(user)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "No se puede eliminar: el usuario tiene historial asociado (auditoría, despliegues, etc.). "
                "Desactívalo en su lugar."
            ),
        ) from exc
    log_action(
        db, current_user, "user.deleted", "user", user_id,
        details={"dni": deleted_dni, "username": deleted_username}, request=request,
    )
