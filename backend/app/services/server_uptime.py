"""Per-server connectivity uptime, derived from the same "Servidor reconectado"/
"Servidor desconectado" InAppNotification rows already written by
incident_notifier.notify_incident on every agent connect/disconnect (see
agents.py's websocket handler) — no separate connectivity log table needed, this
just reads the notification history that already exists for a different reason.
"""

import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import or_, select
from sqlalchemy.orm import Session, selectinload

from app.models.infrastructure import Server, ServerStatus, Site
from app.models.monitoring import AlertSeverity, InAppNotification
from app.schemas.server import (
    CriticalConnectivityAlert,
    FleetConnectivityEvent,
    ServerConnectivitySummary,
    ServerOutage,
    ServerUptimeSummary,
)

_RECONNECTED_PREFIX = "Servidor reconectado"
_DISCONNECTED_PREFIX = "Servidor desconectado"
_CONNECTIVITY_TITLE_FILTER = or_(
    InAppNotification.title.like(f"{_RECONNECTED_PREFIX}%"),
    InAppNotification.title.like(f"{_DISCONNECTED_PREFIX}%"),
)


def _dedup(rows: list[InAppNotification]) -> list[InAppNotification]:
    """notify_incident writes one InAppNotification row per recipient for the same
    event — dedup by (title, created_at), same approach _collapse_connectivity_flaps
    (recent-activity endpoint) already uses for this exact table."""
    seen: set[tuple] = set()
    out: list[InAppNotification] = []
    for row in rows:
        key = (row.title, row.created_at)
        if key in seen:
            continue
        seen.add(key)
        out.append(row)
    return out


def compute_uptime_summary(db: Session, server: Server, days: int) -> ServerUptimeSummary:
    now = datetime.now(timezone.utc)
    window_start = now - timedelta(days=days)

    seed = db.scalars(
        select(InAppNotification)
        .where(
            InAppNotification.entity_type == "server",
            InAppNotification.entity_id == str(server.id),
            InAppNotification.created_at <= window_start,
            _CONNECTIVITY_TITLE_FILTER,
        )
        .order_by(InAppNotification.created_at.desc())
        .limit(1)
    ).first()

    events = _dedup(
        list(
            db.scalars(
                select(InAppNotification)
                .where(
                    InAppNotification.entity_type == "server",
                    InAppNotification.entity_id == str(server.id),
                    InAppNotification.created_at > window_start,
                    _CONNECTIVITY_TITLE_FILTER,
                )
                .order_by(InAppNotification.created_at)
            )
        )
    )

    if seed is not None:
        state = "online" if seed.title.startswith(_RECONNECTED_PREFIX) else "offline"
    else:
        # No connectivity history before this window at all — best available guess is that
        # the server has been in whatever its currently recorded status is for the whole
        # window (matters mainly right after this feature ships, before real history
        # accumulates).
        state = "online" if server.status == ServerStatus.online else "offline"

    outages: list[ServerOutage] = []
    current_outage_start: datetime | None = window_start if state == "offline" else None

    for row in events:
        if row.title.startswith(_DISCONNECTED_PREFIX) and state == "online":
            current_outage_start = row.created_at
            state = "offline"
        elif row.title.startswith(_RECONNECTED_PREFIX) and state == "offline":
            if current_outage_start is not None:
                outages.append(
                    ServerOutage(
                        started_at=current_outage_start,
                        ended_at=row.created_at,
                        duration_seconds=int((row.created_at - current_outage_start).total_seconds()),
                    )
                )
            current_outage_start = None
            state = "online"

    if state == "offline" and current_outage_start is not None:
        outages.append(
            ServerOutage(
                started_at=current_outage_start,
                ended_at=None,
                duration_seconds=int((now - current_outage_start).total_seconds()),
            )
        )

    window_seconds = (now - window_start).total_seconds()
    offline_seconds = sum(o.duration_seconds for o in outages)
    uptime_percent = max(0.0, min(100.0, (1 - offline_seconds / window_seconds) * 100)) if window_seconds > 0 else 100.0

    outages.reverse()  # most recent first, matching every other list in this app
    return ServerUptimeSummary(window_days=days, uptime_percent=round(uptime_percent, 2), outages=outages)


def _connectivity_rows_since(db: Session, since: datetime) -> list[InAppNotification]:
    """Every deduped 'Servidor desconectado'/'Servidor reconectado' InAppNotification
    row across the whole fleet since `since`, newest first — the shared raw material for
    both compute_fleet_connectivity_events (flat timeline) and
    compute_fleet_connectivity_summary (one row per server) below."""
    return _dedup(
        list(
            db.scalars(
                select(InAppNotification)
                .where(
                    InAppNotification.entity_type == "server",
                    InAppNotification.created_at >= since,
                    _CONNECTIVITY_TITLE_FILTER,
                )
                .order_by(InAppNotification.created_at.desc())
            )
        )
    )


def compute_fleet_connectivity_events(
    db: Session,
    site_ids: list[uuid.UUID] | None,
    days: int,
    *,
    event_type_filter: str | None = None,
    site_id_filter: uuid.UUID | None = None,
    server_id_filter: uuid.UUID | None = None,
    search: str | None = None,
    limit: int = 50,
) -> list[FleetConnectivityEvent]:
    """Flat, fleet-wide timeline of every 'Servidor desconectado'/'Servidor reconectado'
    event across all visible servers — the consolidated counterpart to
    compute_uptime_summary above, which is scoped to one server at a time. Reuses the
    exact same InAppNotification rows (no separate connectivity log table), same
    per-recipient dedup, same title-prefix convention. Passing server_id_filter narrows
    this to one server's full raw event log (used by the per-server connectivity page —
    distinct from compute_uptime_summary's outage-pairing, this keeps every raw event
    including its 'Motivo: ...' text)."""
    since = datetime.now(timezone.utc) - timedelta(days=days)

    servers = {s.id: s for s in db.scalars(select(Server).options(selectinload(Server.site)))}
    rows = _connectivity_rows_since(db, since)

    term = search.strip().lower() if search else None
    events: list[FleetConnectivityEvent] = []
    for row in rows:
        if row.entity_id is None:
            continue
        try:
            server_id = uuid.UUID(row.entity_id)
        except ValueError:
            continue
        if server_id_filter is not None and server_id != server_id_filter:
            continue
        server = servers.get(server_id)
        if server is None:
            continue
        if site_ids is not None and server.site_id not in site_ids:
            continue
        if site_id_filter is not None and server.site_id != site_id_filter:
            continue
        event_type = "reconnected" if row.title.startswith(_RECONNECTED_PREFIX) else "disconnected"
        if event_type_filter is not None and event_type != event_type_filter:
            continue
        if term and term not in server.hostname.lower():
            continue
        events.append(
            FleetConnectivityEvent(
                id=f"{server.id}:{row.created_at.isoformat()}",
                server_id=server.id,
                hostname=server.hostname,
                site_id=server.site_id,
                site_name=server.site.name if server.site is not None else None,
                event_type=event_type,
                occurred_at=row.created_at,
                message=row.message,
            )
        )
        if len(events) >= limit:
            break

    return events


def compute_fleet_connectivity_summary(
    db: Session, site_ids: list[uuid.UUID] | None, days: int
) -> list["ServerConnectivitySummary"]:
    """One row per visible server for the /connectivity server-list page — current
    status, uptime% over the window, how many times it dropped, and its most recent
    connectivity event — so a técnico can scan the whole fleet without opening every
    server, then drill into just the ones that need it. Sorted worst-uptime-first (nulls
    — servers that have never actually connected even once — last) so problems surface
    at the top."""
    since = datetime.now(timezone.utc) - timedelta(days=days)

    servers = list(db.scalars(select(Server).options(selectinload(Server.site), selectinload(Server.agent))))
    if site_ids is not None:
        servers = [s for s in servers if s.site_id in site_ids]

    rows = _connectivity_rows_since(db, since)
    events_by_server: dict[uuid.UUID, list[InAppNotification]] = {}
    for row in rows:
        if row.entity_id is None:
            continue
        try:
            server_id = uuid.UUID(row.entity_id)
        except ValueError:
            continue
        events_by_server.setdefault(server_id, []).append(row)

    summaries: list[ServerConnectivitySummary] = []
    for server in servers:
        server_events = events_by_server.get(server.id, [])
        # last_heartbeat_at (not just "has an Agent row") distinguishes "has actually
        # connected at least once" from "an enrollment token was issued but install never
        # completed" (e.g. the Alzamora servers blocked on a missing Windows Update) —
        # the latter would otherwise show a misleading 0% instead of "never connected".
        has_ever_connected = server.agent is not None and server.agent.last_heartbeat_at is not None
        uptime_percent = compute_uptime_summary(db, server, days).uptime_percent if has_ever_connected else None
        last_event = server_events[0] if server_events else None
        summaries.append(
            ServerConnectivitySummary(
                server_id=server.id,
                hostname=server.hostname,
                site_id=server.site_id,
                site_name=server.site.name if server.site is not None else None,
                status=server.status,
                uptime_percent=uptime_percent,
                outage_count=sum(1 for e in server_events if e.title.startswith(_DISCONNECTED_PREFIX)),
                last_event_type=(
                    "reconnected" if last_event is not None and last_event.title.startswith(_RECONNECTED_PREFIX) else "disconnected"
                )
                if last_event is not None
                else None,
                last_event_at=last_event.created_at if last_event is not None else None,
                last_event_message=last_event.message if last_event is not None else None,
            )
        )

    summaries.sort(key=lambda s: (s.uptime_percent if s.uptime_percent is not None else 101, s.hostname))
    return summaries


def list_active_connectivity_alerts(
    db: Session, user_id: uuid.UUID, site_ids: list[uuid.UUID] | None
) -> list[CriticalConnectivityAlert]:
    """Backs the critical-alert banner/modal's connectivity feed — unlike the threshold
    AlertRule/AlertEvent pipeline (which has an explicit open/resolved status), an
    InAppNotification has no per-event "resolved" state, so "currently active" here is
    defined as: the server is offline right now AND this user hasn't marked its most
    recent disconnect notification as read (POST /in-app-notifications/{id}/read is
    reused as the "acknowledge" action — no new acknowledgement concept needed).
    Deliberately self-clears the moment a server reconnects (Server.status flips to
    online), so a flapping agent can't keep re-triggering the modal/banner for an outage
    that's already over — no separate cooldown window needed."""
    rows = list(
        db.scalars(
            select(InAppNotification)
            .where(
                InAppNotification.recipient_id == user_id,
                InAppNotification.read_at.is_(None),
                InAppNotification.severity == AlertSeverity.critical,
                InAppNotification.entity_type == "server",
                InAppNotification.title.like(f"{_DISCONNECTED_PREFIX}%"),
            )
            .order_by(InAppNotification.created_at.desc())
        )
    )

    seen_servers: set[uuid.UUID] = set()
    alerts: list[CriticalConnectivityAlert] = []
    for row in rows:
        if row.entity_id is None:
            continue
        try:
            server_id = uuid.UUID(row.entity_id)
        except ValueError:
            continue
        if server_id in seen_servers:
            continue
        seen_servers.add(server_id)

        server = db.get(Server, server_id)
        if server is None or server.status != ServerStatus.offline:
            continue
        if site_ids is not None and server.site_id not in site_ids:
            continue

        site = db.get(Site, server.site_id) if server.site_id is not None else None
        alerts.append(
            CriticalConnectivityAlert(
                id=row.id,
                server_id=server.id,
                hostname=server.hostname,
                site_name=site.name if site is not None else None,
                occurred_at=row.created_at,
                message=row.message,
            )
        )

    alerts.sort(key=lambda a: a.occurred_at, reverse=True)
    return alerts
