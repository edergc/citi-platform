import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.api.deps import get_current_user, require_permission
from app.core.database import get_db
from app.models.identity import Permission, Role, User, UserRoleAssignment
from app.schemas.role import PermissionRead, RoleCreate, RoleRead, RoleUpdate
from app.services.audit import diff_changed_fields, log_action

router = APIRouter(tags=["roles"], dependencies=[Depends(get_current_user)])

_manage = Depends(require_permission("roles.manage"))


def _to_read(role: Role) -> RoleRead:
    return RoleRead(
        id=role.id,
        name=role.name,
        description=role.description,
        is_system_role=role.is_system_role,
        permission_codes=sorted(p.code for p in role.permissions),
    )


def _resolve_permissions(db: Session, codes: list[str]) -> list[Permission]:
    if not codes:
        return []
    permissions = list(db.scalars(select(Permission).where(Permission.code.in_(codes))))
    found = {p.code for p in permissions}
    missing = set(codes) - found
    if missing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=f"Permisos desconocidos: {', '.join(sorted(missing))}"
        )
    return permissions


@router.get("/permissions", response_model=list[PermissionRead])
def list_permissions(db: Session = Depends(get_db)) -> list[Permission]:
    return list(db.scalars(select(Permission).order_by(Permission.code)))


@router.get("/roles", response_model=list[RoleRead])
def list_roles(db: Session = Depends(get_db)) -> list[RoleRead]:
    roles = db.scalars(select(Role).options(selectinload(Role.permissions)).order_by(Role.name)).all()
    return [_to_read(r) for r in roles]


@router.post("/roles", response_model=RoleRead, status_code=status.HTTP_201_CREATED, dependencies=[_manage])
def create_role(
    payload: RoleCreate, request: Request, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)
) -> RoleRead:
    permissions = _resolve_permissions(db, payload.permission_codes)
    role = Role(name=payload.name, description=payload.description, permissions=permissions)
    db.add(role)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Ya existe un perfil con ese nombre") from exc
    db.refresh(role)
    log_action(
        db, current_user, "role.created", "role", role.id,
        details={"name": role.name, "permission_codes": payload.permission_codes}, request=request,
    )
    return _to_read(role)


@router.patch("/roles/{role_id}", response_model=RoleRead, dependencies=[_manage])
def update_role(
    role_id: uuid.UUID,
    payload: RoleUpdate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> RoleRead:
    role = db.get(Role, role_id, options=[selectinload(Role.permissions)])
    if role is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Perfil no encontrado")

    data = payload.model_dump(exclude_unset=True)
    if role.is_system_role and ("name" in data or "permission_codes" in data):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="El perfil Administrador no puede modificarse"
        )

    changes = diff_changed_fields(role, {k: v for k, v in data.items() if k in ("name", "description")})

    if "name" in data:
        role.name = data["name"]
    if "description" in data:
        role.description = data["description"]
    if "permission_codes" in data:
        old_codes = sorted(p.code for p in role.permissions)
        new_codes = sorted(data["permission_codes"] or [])
        if old_codes != new_codes:
            changes["permission_codes"] = {"antes": old_codes, "despues": new_codes}
        role.permissions = _resolve_permissions(db, data["permission_codes"] or [])

    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Ya existe un perfil con ese nombre") from exc
    db.refresh(role)
    log_action(
        db, current_user, "role.updated", "role", role.id, details={"changes": changes} if changes else None, request=request
    )
    return _to_read(role)


@router.delete("/roles/{role_id}", status_code=status.HTTP_204_NO_CONTENT, dependencies=[_manage])
def delete_role(
    role_id: uuid.UUID, request: Request, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)
) -> None:
    role = db.get(Role, role_id)
    if role is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Perfil no encontrado")
    if role.is_system_role:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="El perfil Administrador no puede eliminarse")

    assigned = db.scalar(select(UserRoleAssignment.id).where(UserRoleAssignment.role_id == role_id).limit(1))
    if assigned is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="No se puede eliminar: hay usuarios con este perfil asignado. Reasígnalos primero.",
        )

    deleted_name = role.name
    db.delete(role)
    db.commit()
    log_action(db, current_user, "role.deleted", "role", role_id, details={"name": deleted_name}, request=request)
