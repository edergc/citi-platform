"""Maintenance window lookups shared by the notification-suppression check in
app.services.incident_notifier and by the `active_maintenance` field exposed on
ServerRead (app.api.v1.servers) — one place computing "is X under a planned window right
now" so both stay consistent.
"""

import uuid
from datetime import datetime, timezone
from typing import Literal

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.models.infrastructure import Server, Site
from app.models.monitoring import MaintenanceScope, MaintenanceWindow

MaintenanceStatus = Literal["scheduled", "active", "ended", "cancelled"]


def resolve_scope(db: Session, scope_type: MaintenanceScope, scope_id: uuid.UUID) -> tuple[str, uuid.UUID | None]:
    """Returns (scope_label, effective_site_id) — a server's effective site is the site
    it belongs to; a site's effective site is itself. Shared by the maintenance-windows
    router (labeling + site-visibility checks) and the fleet dashboard (labeling only)."""
    if scope_type == MaintenanceScope.server:
        server = db.get(Server, scope_id)
        return (server.hostname if server else "servidor eliminado"), (server.site_id if server else None)
    site = db.get(Site, scope_id)
    return (site.name if site else "sede eliminada"), scope_id


def compute_status(window: MaintenanceWindow, *, now: datetime | None = None) -> MaintenanceStatus:
    if window.cancelled_at is not None:
        return "cancelled"
    now = now or datetime.now(timezone.utc)
    if now < window.starts_at:
        return "scheduled"
    if now <= window.ends_at:
        return "active"
    return "ended"


def list_active_windows(db: Session) -> list[MaintenanceWindow]:
    """This table is small by nature (a handful of windows open across the whole fleet
    at any moment) — loading all of them and matching in Python, both here and in the
    bulk server-list case, is simpler than building an OR-of-scopes query per caller and
    still cheap."""
    now = datetime.now(timezone.utc)
    return list(
        db.scalars(
            select(MaintenanceWindow).where(
                MaintenanceWindow.cancelled_at.is_(None),
                MaintenanceWindow.starts_at <= now,
                MaintenanceWindow.ends_at >= now,
            )
        )
    )


def find_active_window(
    db: Session, *, server_id: uuid.UUID | None, site_id: uuid.UUID | None
) -> MaintenanceWindow | None:
    """Returns the active window covering this server (matched directly by server_id, or
    by the site_id of the site it belongs to), or None. Only one is returned even if
    both a server-scoped and a site-scoped window happen to overlap — callers only need
    to know "is this suppressed right now", not every reason why."""
    if server_id is None and site_id is None:
        return None
    for window in list_active_windows(db):
        if window.scope_type == MaintenanceScope.server and window.scope_id == server_id:
            return window
        if site_id is not None and window.scope_type == MaintenanceScope.site and window.scope_id == site_id:
            return window
    return None


def _covers(window: MaintenanceWindow, at: datetime) -> bool:
    if window.cancelled_at is not None and window.cancelled_at <= at:
        return False
    return window.starts_at <= at <= window.ends_at


def bulk_maintenance_windows(
    db: Session, *, server_ids: set[uuid.UUID], site_ids: set[uuid.UUID]
) -> tuple[dict[uuid.UUID, list[MaintenanceWindow]], dict[uuid.UUID, list[MaintenanceWindow]]]:
    """Every window (of any status, past or present) scoped to one of the given
    server/site ids — used to answer "was this server under maintenance at time T" for
    historical AlertEvent rows, not just "is it under maintenance right now". Returns
    (windows_by_server_id, windows_by_site_id)."""
    by_server: dict[uuid.UUID, list[MaintenanceWindow]] = {}
    by_site: dict[uuid.UUID, list[MaintenanceWindow]] = {}
    if not server_ids and not site_ids:
        return by_server, by_site

    conditions = []
    if server_ids:
        conditions.append((MaintenanceWindow.scope_type == MaintenanceScope.server) & MaintenanceWindow.scope_id.in_(server_ids))
    if site_ids:
        conditions.append((MaintenanceWindow.scope_type == MaintenanceScope.site) & MaintenanceWindow.scope_id.in_(site_ids))

    for window in db.scalars(select(MaintenanceWindow).where(or_(*conditions))):
        target = by_server if window.scope_type == MaintenanceScope.server else by_site
        target.setdefault(window.scope_id, []).append(window)
    return by_server, by_site


def was_under_maintenance(
    windows_by_server: dict[uuid.UUID, list[MaintenanceWindow]],
    windows_by_site: dict[uuid.UUID, list[MaintenanceWindow]],
    *,
    server_id: uuid.UUID | None,
    site_id: uuid.UUID | None,
    at: datetime,
) -> bool:
    if server_id is not None and any(_covers(w, at) for w in windows_by_server.get(server_id, [])):
        return True
    if site_id is not None and any(_covers(w, at) for w in windows_by_site.get(site_id, [])):
        return True
    return False
