import uuid
from typing import Callable

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import decode_token
from app.models.identity import Permission, Role, RolePermission, User, UserRoleAssignment

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")


def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)) -> User:
    credentials_error = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Credenciales inválidas",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = decode_token(token)
        if payload.get("type") != "access":
            raise credentials_error
        user_id = uuid.UUID(payload["sub"])
    except (JWTError, KeyError, ValueError) as exc:
        raise credentials_error from exc

    user = db.get(User, user_id)
    if user is None or not user.is_active:
        raise credentials_error
    return user


def require_superuser(user: User = Depends(get_current_user)) -> User:
    if not user.is_superuser:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Requiere privilegios de administrador")
    return user


def user_has_permission(db: Session, user: User, code: str) -> bool:
    if user.is_superuser:
        return True
    stmt = (
        select(Permission.id)
        .join(RolePermission, RolePermission.permission_id == Permission.id)
        .join(Role, Role.id == RolePermission.role_id)
        .join(UserRoleAssignment, UserRoleAssignment.role_id == Role.id)
        .where(UserRoleAssignment.user_id == user.id, Permission.code == code)
        .limit(1)
    )
    return db.scalar(stmt) is not None


def require_permission(code: str) -> Callable[[User, Session], User]:
    """Dependency factory: allows superusers unconditionally, otherwise requires a role
    assignment granting the given permission code."""

    def dependency(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> User:
        if not user_has_permission(db, user, code):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="No tienes el privilegio requerido")
        return user

    return dependency


def get_visible_site_ids(current_user: User = Depends(get_current_user)) -> list[uuid.UUID] | None:
    """None = unrestricted (superuser) — caller sees everything. Otherwise the list of
    sedes the current user belongs to; an empty list is valid and means 'sees nothing
    yet' (no sedes assigned). Used to scope which servers a technician can see/manage."""
    if current_user.is_superuser:
        return None
    return [site.id for site in current_user.sites]
