"""Builds the enriched UserRead (site names, global role name) shared by /auth/me and the users admin API."""

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.identity import Role, User, UserRoleAssignment, UserSite
from app.models.infrastructure import Site
from app.schemas.user import UserRead


def user_sites_map(db: Session) -> dict[uuid.UUID, list[tuple[uuid.UUID, str]]]:
    """user_id -> [(site_id, site_name), ...] sorted by name, for bulk endpoints like list_users."""
    rows = db.execute(
        select(UserSite.user_id, Site.id, Site.name).join(Site, Site.id == UserSite.site_id).order_by(Site.name)
    ).all()
    result: dict[uuid.UUID, list[tuple[uuid.UUID, str]]] = {}
    for user_id, site_id, name in rows:
        result.setdefault(user_id, []).append((site_id, name))
    return result


def global_role_map(db: Session) -> dict[uuid.UUID, Role]:
    """Maps user_id -> Role for each user's global (non system-scoped) role assignment."""
    rows = db.execute(
        select(UserRoleAssignment.user_id, Role)
        .join(Role, Role.id == UserRoleAssignment.role_id)
        .where(UserRoleAssignment.scope_system_id.is_(None))
    ).all()
    result: dict[uuid.UUID, Role] = {}
    for user_id, role in rows:
        result.setdefault(user_id, role)
    return result


def to_user_read(user: User, sites: dict[uuid.UUID, list[tuple[uuid.UUID, str]]], roles: dict[uuid.UUID, Role]) -> UserRead:
    role = roles.get(user.id)
    user_sites = sites.get(user.id, [])
    return UserRead(
        id=user.id,
        dni=user.dni,
        email=user.email,
        username=user.username,
        full_name=user.full_name,
        phone=user.phone,
        site_ids=[s[0] for s in user_sites],
        site_names=[s[1] for s in user_sites],
        role_id=role.id if role else None,
        role_name=role.name if role else None,
        permission_codes=sorted(p.code for p in role.permissions) if role else [],
        is_active=user.is_active,
        is_superuser=user.is_superuser,
        mfa_enabled=user.mfa_enabled,
        last_login_at=user.last_login_at,
        created_at=user.created_at,
    )


def build_user_read(db: Session, user: User) -> UserRead:
    """Single-user variant: avoids loading every site/role for a one-off lookup (e.g. /auth/me)."""
    user_sites = sorted(user.sites, key=lambda s: s.name)

    role = db.scalar(
        select(Role)
        .join(UserRoleAssignment, UserRoleAssignment.role_id == Role.id)
        .where(UserRoleAssignment.user_id == user.id, UserRoleAssignment.scope_system_id.is_(None))
        .limit(1)
    )

    return UserRead(
        id=user.id,
        dni=user.dni,
        email=user.email,
        username=user.username,
        full_name=user.full_name,
        phone=user.phone,
        site_ids=[s.id for s in user_sites],
        site_names=[s.name for s in user_sites],
        role_id=role.id if role else None,
        role_name=role.name if role else None,
        permission_codes=sorted(p.code for p in role.permissions) if role else [],
        is_active=user.is_active,
        is_superuser=user.is_superuser,
        mfa_enabled=user.mfa_enabled,
        last_login_at=user.last_login_at,
        created_at=user.created_at,
    )
