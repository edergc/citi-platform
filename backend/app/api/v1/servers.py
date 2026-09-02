import uuid
from datetime import datetime, timedelta, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.api.deps import get_current_user, get_visible_site_ids, require_superuser
from app.core.database import get_db
from app.models.identity import User
from app.models.infrastructure import (
    Agent,
    AgentStatus,
    Server,
    ServerEvent,
    ServerMetricHistory,
    ServerNote,
    ServerStatus,
    Site,
)
from app.models.monitoring import InAppNotification, MaintenanceScope
from app.models.systems import Service, ServiceActionLog
from app.schemas.dashboard import FleetDashboard
from app.schemas.network_path import NetworkLatencySparkline, NetworkPathFleetRow, NetworkPathHistory
from app.schemas.server import (
    BreachingServer,
    CriticalConnectivityAlert,
    DiskForecast,
    FleetAgentStatusCounts,
    FleetConnectivityEvent,
    FleetStatusCounts,
    FleetSummary,
    ServerActivityItem,
    ServerConnectivitySummary,
    ServerCreate,
    ServerEventRead,
    ServerMetricHistoryPoint,
    ServerMetricsRead,
    ServerNoteCreate,
    ServerNoteRead,
    ServerRead,
    ServerSparkline,
    ServerSparklinePoint,
    ServerUpdate,
    ServerUptimeSummary,
    SiteAverage,
)
from app.services.audit import diff_changed_fields, log_action
from app.services.disk_forecast import compute_disk_forecast
from app.services.fleet_dashboard import compute_fleet_dashboard
from app.services.maintenance_windows import list_active_windows
from app.services.metric_thresholds import is_breaching, load_applicable_rules
from app.services.network_path import compute_fleet_network_path, compute_network_latency_sparklines, compute_network_path
from app.services.server_health import compute_health, compute_health_map
from app.services.server_uptime import (
    compute_fleet_connectivity_events,
    compute_fleet_connectivity_summary,
    compute_uptime_summary,
    list_active_connectivity_alerts,
)

_SEVERITY_RANK = {"critical": 0, "warning": 1, "info": 2}

router = APIRouter(prefix="/servers", tags=["servers"], dependencies=[Depends(get_current_user)])


def _ensure_visible(server: Server, site_ids: list[uuid.UUID] | None) -> None:
    """site_ids=None means the caller is a superuser (unrestricted). Otherwise a server
    with no site, or a site outside the caller's own sedes, doesn't exist as far as
    they're concerned — 404, not 403, matching how missing resources already read here."""
    if site_ids is not None and (server.site_id is None or server.site_id not in site_ids):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Servidor no encontrado")


def _attach_responsible_name(server: Server) -> Server:
    server.primary_responsible_user_name = (
        server.primary_responsible_user.full_name if server.primary_responsible_user else None
    )
    return server


def _attach_health(db: Session, server: Server) -> Server:
    result = compute_health(db, server)
    server.health = result.status
    server.health_reasons = result.reasons
    return server


def _attach_health_bulk(db: Session, servers: list[Server]) -> list[Server]:
    health_map = compute_health_map(db, servers)
    for server in servers:
        result = health_map[server.id]
        server.health = result.status
        server.health_reasons = result.reasons
    return servers


def _attach_maintenance_bulk(db: Session, servers: list[Server]) -> list[Server]:
    windows = list_active_windows(db)
    by_server = {w.scope_id: w for w in windows if w.scope_type == MaintenanceScope.server}
    by_site = {w.scope_id: w for w in windows if w.scope_type == MaintenanceScope.site}
    for server in servers:
        server.active_maintenance = by_server.get(server.id) or (by_site.get(server.site_id) if server.site_id else None)
    return servers


def _validate_responsible_user(db: Session, user_id: uuid.UUID | None) -> None:
    if user_id is None:
        return
    user = db.get(User, user_id)
    if user is None or not user.is_active:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Usuario responsable no válido")


@router.get("", response_model=list[ServerRead])
def list_servers(
    db: Session = Depends(get_db), site_ids: list[uuid.UUID] | None = Depends(get_visible_site_ids)
) -> list[Server]:
    query = select(Server).options(selectinload(Server.primary_responsible_user)).order_by(Server.hostname)
    if site_ids is not None:
        query = query.where(Server.site_id.in_(site_ids))
    servers = [_attach_responsible_name(s) for s in db.scalars(query)]
    return _attach_maintenance_bulk(db, _attach_health_bulk(db, servers))


@router.get("/sparklines", response_model=list[ServerSparkline])
def get_server_sparklines(
    hours: int = 6, db: Session = Depends(get_db), site_ids: list[uuid.UUID] | None = Depends(get_visible_site_ids)
) -> list[ServerSparkline]:
    """One bulk query for every visible server's recent CPU/RAM trend, instead of the
    servers list making one request per row — backs the tiny inline sparklines in the
    Lista table."""
    hours = max(1, min(hours, 72))
    since = datetime.now(timezone.utc) - timedelta(hours=hours)

    server_query = select(Server.id)
    if site_ids is not None:
        server_query = server_query.where(Server.site_id.in_(site_ids))
    visible_ids = set(db.scalars(server_query))
    if not visible_ids:
        return []

    rows = db.scalars(
        select(ServerMetricHistory)
        .where(ServerMetricHistory.server_id.in_(visible_ids), ServerMetricHistory.recorded_at >= since)
        .order_by(ServerMetricHistory.recorded_at)
    )
    by_server: dict[uuid.UUID, list[ServerSparklinePoint]] = {}
    for row in rows:
        by_server.setdefault(row.server_id, []).append(
            ServerSparklinePoint(recorded_at=row.recorded_at, cpu_percent=row.cpu_percent, ram_percent=row.ram_percent)
        )
    return [ServerSparkline(server_id=server_id, points=points) for server_id, points in by_server.items()]


@router.get("/network-path-summary", response_model=list[NetworkPathFleetRow])
def get_network_path_summary(
    db: Session = Depends(get_db), site_ids: list[uuid.UUID] | None = Depends(get_visible_site_ids)
) -> list[NetworkPathFleetRow]:
    """Fleet-wide network status board — the latest network-path sample per visible
    server, one request. Same visibility tier as GET /servers itself (site-scoped,
    not require_superuser): a técnico should see this for their own sites same as the
    per-server diagnostics card already does."""
    return compute_fleet_network_path(db, site_ids)


@router.get("/network-path-sparklines", response_model=list[NetworkLatencySparkline])
def get_network_path_sparklines(
    hours: int = 6, db: Session = Depends(get_db), site_ids: list[uuid.UUID] | None = Depends(get_visible_site_ids)
) -> list[NetworkLatencySparkline]:
    hours = max(1, min(hours, 72))
    return compute_network_latency_sparklines(db, site_ids, hours)


@router.post("", response_model=ServerRead, status_code=status.HTTP_201_CREATED, dependencies=[Depends(require_superuser)])
def create_server(
    payload: ServerCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    site_ids: list[uuid.UUID] | None = Depends(get_visible_site_ids),
) -> Server:
    if site_ids is not None and payload.site_id is not None and payload.site_id not in site_ids:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="No puedes crear un servidor fuera de tus sedes asignadas"
        )
    _validate_responsible_user(db, payload.primary_responsible_user_id)
    server = Server(**payload.model_dump())
    db.add(server)
    db.commit()
    db.refresh(server)
    log_action(
        db, current_user, "server.created", "server", server.id, details={"hostname": server.hostname}, request=request
    )
    return _attach_health(db, _attach_responsible_name(server))


@router.get("/fleet-summary", response_model=FleetSummary)
def get_fleet_summary(
    db: Session = Depends(get_db), site_ids: list[uuid.UUID] | None = Depends(get_visible_site_ids)
) -> FleetSummary:
    """Read-only aggregate view backing the Servers 'Resumen' dashboard: connectivity/agent
    counts, server count per site, and every server currently breaching an applicable
    AlertRule (reusing the same pure evaluation helpers the heartbeat handler uses, just
    without cooldown/persistence side effects).

    Deliberately no per-site average CPU/RAM here — with several servers per site, an
    average doesn't say which one needs attention, and reads as if it were a single
    live reading. Per-server usage belongs in the Lista tab instead (see
    get_server_sparklines), not as a site-level rollup."""
    query = select(Server)
    if site_ids is not None:
        query = query.where(Server.site_id.in_(site_ids))
    servers = list(db.scalars(query))
    agents_by_server = {a.server_id: a for a in db.scalars(select(Agent))}
    site_names = {s.id: s.name for s in db.scalars(select(Site))}

    status_counts = {s.value: 0 for s in ServerStatus}
    agent_status_counts = {s.value: 0 for s in AgentStatus}
    site_counts: dict[uuid.UUID | None, int] = {}

    for server in servers:
        status_counts[server.status.value] += 1
        agent = agents_by_server.get(server.id)
        if agent is not None:
            agent_status_counts[agent.status.value] += 1

        site_counts[server.site_id] = site_counts.get(server.site_id, 0) + 1

    site_averages = [
        SiteAverage(
            site_id=site_id,
            site_name=site_names.get(site_id) if site_id else None,
            server_count=count,
        )
        for site_id, count in site_counts.items()
    ]

    breaching: list[BreachingServer] = []
    for server in servers:
        agent = agents_by_server.get(server.id)
        if agent is None:
            continue
        metrics = {"ram_percent": agent.ram_percent, "cpu_percent": agent.cpu_percent, "disks": agent.disks}
        for rule in load_applicable_rules(db, server.id):
            hit, value, mount = is_breaching(rule, metrics)
            if not hit:
                continue
            breaching.append(
                BreachingServer(
                    server_id=server.id,
                    hostname=server.hostname,
                    site_name=site_names.get(server.site_id) if server.site_id else None,
                    rule_name=rule.name,
                    metric=rule.metric,
                    mount=mount,
                    severity=rule.severity.value,
                    value=value,
                    threshold=rule.threshold,
                )
            )
    breaching.sort(key=lambda b: _SEVERITY_RANK.get(b.severity, 99))

    return FleetSummary(
        status_counts=FleetStatusCounts(**status_counts),
        agent_status_counts=FleetAgentStatusCounts(**agent_status_counts),
        site_averages=site_averages,
        breaching_servers=breaching,
    )


@router.get("/dashboard", response_model=FleetDashboard, dependencies=[Depends(require_superuser)])
def get_fleet_dashboard(db: Session = Depends(get_db)) -> FleetDashboard:
    """Cross-site aggregate analysis (OS comparison, sede ranking, alert trend, top
    offenders) for the admin-only Dashboards page — always fleet-wide by design, so
    unlike every other endpoint here it does not take get_visible_site_ids at all."""
    return compute_fleet_dashboard(db)


@router.get("/critical-connectivity-alerts", response_model=list[CriticalConnectivityAlert])
def get_critical_connectivity_alerts(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    site_ids: list[uuid.UUID] | None = Depends(get_visible_site_ids),
) -> list[CriticalConnectivityAlert]:
    """Backs the critical-alert banner/modal (see CriticalAlertBanner.tsx/CriticalAlertModal.tsx)
    — currently-offline servers whose disconnect notification this user hasn't
    acknowledged yet. 'Acknowledge' here just means POST /in-app-notifications/{id}/read
    on the id returned here, reusing the bell's existing mark-read endpoint."""
    return list_active_connectivity_alerts(db, current_user.id, site_ids)


@router.get("/connectivity-summary", response_model=list[ServerConnectivitySummary])
def get_fleet_connectivity_summary(
    days: int = 30,
    db: Session = Depends(get_db),
    site_ids: list[uuid.UUID] | None = Depends(get_visible_site_ids),
) -> list[ServerConnectivitySummary]:
    """One row per visible server — current status, uptime% and last connectivity event —
    backing the /connectivity server list. Deliberately not paginated server-side: the
    whole visible fleet is returned in one call (same approach as GET /servers itself)
    and the frontend paginates client-side, since fleet size here is in the dozens, not
    thousands."""
    days = max(1, min(days, 180))
    return compute_fleet_connectivity_summary(db, site_ids, days)


@router.get("/connectivity-events", response_model=list[FleetConnectivityEvent])
def get_fleet_connectivity_events(
    days: int = 30,
    limit: int = 50,
    event_type_filter: Literal["disconnected", "reconnected"] | None = None,
    site_id_filter: uuid.UUID | None = None,
    server_id_filter: uuid.UUID | None = None,
    search: str | None = None,
    db: Session = Depends(get_db),
    site_ids: list[uuid.UUID] | None = Depends(get_visible_site_ids),
) -> list[FleetConnectivityEvent]:
    """Fleet-wide connectivity event log — every 'Servidor desconectado'/'Servidor
    reconectado' event across all visible servers in one timeline, newest first. Same
    visibility tier as GET /servers (site-scoped, not require_superuser) so a técnico
    sees this for their own sites; distinct from /servers/{id}/uptime (one server's
    outage windows) and /servers/{id}/recent-activity (mixes in service actions too).
    server_id_filter narrows this to one server's full raw event log, used by the
    per-server connectivity detail page (/connectivity/:serverId)."""
    days = max(1, min(days, 180))
    limit = max(1, min(limit, 300))
    return compute_fleet_connectivity_events(
        db,
        site_ids,
        days,
        event_type_filter=event_type_filter,
        site_id_filter=site_id_filter,
        server_id_filter=server_id_filter,
        search=search,
        limit=limit,
    )


@router.get("/{server_id}", response_model=ServerRead)
def get_server(
    server_id: uuid.UUID,
    db: Session = Depends(get_db),
    site_ids: list[uuid.UUID] | None = Depends(get_visible_site_ids),
) -> Server:
    server = db.get(Server, server_id)
    if server is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Servidor no encontrado")
    _ensure_visible(server, site_ids)
    return _attach_maintenance_bulk(db, [_attach_health(db, _attach_responsible_name(server))])[0]


@router.patch("/{server_id}", response_model=ServerRead, dependencies=[Depends(require_superuser)])
def update_server(
    server_id: uuid.UUID,
    payload: ServerUpdate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    site_ids: list[uuid.UUID] | None = Depends(get_visible_site_ids),
) -> Server:
    server = db.get(Server, server_id)
    if server is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Servidor no encontrado")
    _ensure_visible(server, site_ids)
    data = payload.model_dump(exclude_unset=True)
    if "primary_responsible_user_id" in data:
        _validate_responsible_user(db, payload.primary_responsible_user_id)
    changes = diff_changed_fields(server, data)
    for field, value in data.items():
        setattr(server, field, value)
    db.commit()
    db.refresh(server)
    log_action(
        db, current_user, "server.updated", "server", server.id,
        details={"changes": changes} if changes else None, request=request,
    )
    return _attach_health(db, _attach_responsible_name(server))


@router.get("/{server_id}/metrics", response_model=ServerMetricsRead)
def get_server_metrics(
    server_id: uuid.UUID,
    db: Session = Depends(get_db),
    site_ids: list[uuid.UUID] | None = Depends(get_visible_site_ids),
) -> ServerMetricsRead:
    server = db.get(Server, server_id)
    if server is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Servidor no encontrado")
    _ensure_visible(server, site_ids)
    agent = db.scalar(select(Agent).where(Agent.server_id == server_id))
    disk_health = agent.disk_health if agent is not None else None
    return ServerMetricsRead(
        agent_status=agent.status if agent is not None else None,
        last_heartbeat_at=agent.last_heartbeat_at if agent is not None else None,
        metrics_updated_at=agent.metrics_updated_at if agent is not None else None,
        cpu_percent=agent.cpu_percent if agent is not None else None,
        ram_total_mb=agent.ram_total_mb if agent is not None else None,
        ram_used_mb=agent.ram_used_mb if agent is not None else None,
        ram_percent=agent.ram_percent if agent is not None else None,
        disks=agent.disks if agent is not None else None,
        net_bytes_sent=agent.net_bytes_sent if agent is not None else None,
        net_bytes_recv=agent.net_bytes_recv if agent is not None else None,
        uptime_seconds=agent.uptime_seconds if agent is not None else None,
        net_sent_rate_mbps=agent.net_sent_rate_mbps if agent is not None else None,
        net_recv_rate_mbps=agent.net_recv_rate_mbps if agent is not None else None,
        disk_read_mbps=agent.disk_read_mbps if agent is not None else None,
        disk_write_mbps=agent.disk_write_mbps if agent is not None else None,
        disk_io=agent.disk_io if agent is not None else None,
        top_cpu_processes=agent.top_cpu_processes if agent is not None else None,
        top_ram_processes=agent.top_ram_processes if agent is not None else None,
        port_connections=agent.port_connections if agent is not None else None,
        processes_updated_at=agent.processes_updated_at if agent is not None else None,
        agent_version=agent.version if agent is not None else None,
        kernel_version=agent.kernel_version if agent is not None else None,
        cpu_model=agent.cpu_model if agent is not None else None,
        load_average_1m=agent.load_average_1m if agent is not None else None,
        disk_health=(disk_health or {}).get("disks") if disk_health is not None else None,
        disk_health_available=(disk_health or {}).get("available") if disk_health is not None else None,
    )


@router.get("/{server_id}/metrics/history", response_model=list[ServerMetricHistoryPoint])
def get_server_metrics_history(
    server_id: uuid.UUID,
    hours: int = 24,
    db: Session = Depends(get_db),
    site_ids: list[uuid.UUID] | None = Depends(get_visible_site_ids),
) -> list[ServerMetricHistory]:
    server = db.get(Server, server_id)
    if server is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Servidor no encontrado")
    _ensure_visible(server, site_ids)
    hours = max(1, min(hours, 24 * 30))
    since = datetime.now(timezone.utc) - timedelta(hours=hours)
    return list(
        db.scalars(
            select(ServerMetricHistory)
            .where(ServerMetricHistory.server_id == server_id, ServerMetricHistory.recorded_at >= since)
            .order_by(ServerMetricHistory.recorded_at)
        )
    )


@router.get("/{server_id}/uptime", response_model=ServerUptimeSummary)
def get_server_uptime(
    server_id: uuid.UUID,
    days: int = 30,
    db: Session = Depends(get_db),
    site_ids: list[uuid.UUID] | None = Depends(get_visible_site_ids),
) -> ServerUptimeSummary:
    server = db.get(Server, server_id)
    if server is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Servidor no encontrado")
    _ensure_visible(server, site_ids)
    days = max(1, min(days, 90))
    return compute_uptime_summary(db, server, days)


@router.get("/{server_id}/disk-forecast", response_model=DiskForecast)
def get_disk_forecast(
    server_id: uuid.UUID,
    days: int = 14,
    db: Session = Depends(get_db),
    site_ids: list[uuid.UUID] | None = Depends(get_visible_site_ids),
) -> DiskForecast:
    server = db.get(Server, server_id)
    if server is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Servidor no encontrado")
    _ensure_visible(server, site_ids)
    days = max(3, min(days, 90))
    return compute_disk_forecast(db, server_id, days)


@router.get("/{server_id}/network-path", response_model=NetworkPathHistory)
def get_network_path(
    server_id: uuid.UUID,
    hours: int = 6,
    db: Session = Depends(get_db),
    site_ids: list[uuid.UUID] | None = Depends(get_visible_site_ids),
) -> NetworkPathHistory:
    server = db.get(Server, server_id)
    if server is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Servidor no encontrado")
    _ensure_visible(server, site_ids)
    hours = max(1, min(hours, 48))
    return compute_network_path(db, server_id, hours)


@router.get("/{server_id}/notes", response_model=list[ServerNoteRead])
def list_server_notes(
    server_id: uuid.UUID,
    limit: int = 50,
    db: Session = Depends(get_db),
    site_ids: list[uuid.UUID] | None = Depends(get_visible_site_ids),
) -> list[ServerNoteRead]:
    server = db.get(Server, server_id)
    if server is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Servidor no encontrado")
    _ensure_visible(server, site_ids)
    limit = max(1, min(limit, 200))
    notes = list(
        db.scalars(
            select(ServerNote)
            .options(selectinload(ServerNote.author))
            .where(ServerNote.server_id == server_id)
            .order_by(ServerNote.created_at.desc())
            .limit(limit)
        )
    )
    return [
        ServerNoteRead(
            id=n.id,
            server_id=n.server_id,
            author_id=n.author_id,
            author_name=n.author.full_name if n.author else None,
            body=n.body,
            created_at=n.created_at,
        )
        for n in notes
    ]


@router.post("/{server_id}/notes", response_model=ServerNoteRead, status_code=status.HTTP_201_CREATED)
def create_server_note(
    server_id: uuid.UUID,
    payload: ServerNoteCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    site_ids: list[uuid.UUID] | None = Depends(get_visible_site_ids),
) -> ServerNoteRead:
    """Any user who can see this server may add to its bitácora — no separate permission,
    since the point is a durable, low-friction record of what was done and observed."""
    server = db.get(Server, server_id)
    if server is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Servidor no encontrado")
    _ensure_visible(server, site_ids)
    body = payload.body.strip()
    if not body:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="La nota no puede estar vacía")
    note = ServerNote(server_id=server_id, author_id=current_user.id, body=body)
    db.add(note)
    db.commit()
    db.refresh(note)
    return ServerNoteRead(
        id=note.id,
        server_id=note.server_id,
        author_id=note.author_id,
        author_name=current_user.full_name,
        body=note.body,
        created_at=note.created_at,
    )


@router.get("/{server_id}/events", response_model=list[ServerEventRead])
def list_server_events(
    server_id: uuid.UUID,
    limit: int = 50,
    db: Session = Depends(get_db),
    site_ids: list[uuid.UUID] | None = Depends(get_visible_site_ids),
) -> list[ServerEvent]:
    server = db.get(Server, server_id)
    if server is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Servidor no encontrado")
    _ensure_visible(server, site_ids)
    limit = max(1, min(limit, 200))
    return list(
        db.scalars(
            select(ServerEvent)
            .where(ServerEvent.server_id == server_id)
            .order_by(ServerEvent.occurred_at.desc())
            .limit(limit)
        )
    )


def _collapse_connectivity_flaps(items: list[ServerActivityItem]) -> list[ServerActivityItem]:
    """Merges a disconnect immediately followed by its reconnect into one 'interrupción breve'
    row. Without this, every routine agent/service restart shows up as two separate rows (see
    the connect/disconnect notify_incident() calls in agents.py's websocket handler), which
    dominates the feed with noise that isn't actually informative on its own."""
    collapsed: list[ServerActivityItem] = []
    i = 0
    while i < len(items):
        item = items[i]
        next_item = items[i + 1] if i + 1 < len(items) else None
        if (
            item.kind == "notification"
            and item.title.startswith("Servidor reconectado")
            and next_item is not None
            and next_item.kind == "notification"
            and next_item.title.startswith("Servidor desconectado")
        ):
            reconnect, disconnect = item, next_item
            gap_seconds = int((reconnect.occurred_at - disconnect.occurred_at).total_seconds())
            collapsed.append(
                ServerActivityItem(
                    kind="notification",
                    occurred_at=reconnect.occurred_at,
                    title="Interrupción breve de conectividad",
                    detail=f"El servidor estuvo desconectado {gap_seconds}s antes de reconectar.",
                    status="warning" if gap_seconds < 300 else "critical",
                )
            )
            i += 2
            continue
        collapsed.append(item)
        i += 1
    return collapsed


@router.get("/{server_id}/recent-activity", response_model=list[ServerActivityItem])
def get_server_recent_activity(
    server_id: uuid.UUID,
    limit: int = 8,
    db: Session = Depends(get_db),
    site_ids: list[uuid.UUID] | None = Depends(get_visible_site_ids),
) -> list[ServerActivityItem]:
    """Merges service start/stop/restart logs with connectivity and threshold incidents
    raised for this server (see app.services.incident_notifier / metric_thresholds) into
    a single timeline, newest first. Fetches a larger raw pool than `limit` so collapsing
    connectivity flaps (see _collapse_connectivity_flaps) still leaves `limit` rows to return."""
    server = db.get(Server, server_id)
    if server is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Servidor no encontrado")
    _ensure_visible(server, site_ids)
    limit = max(1, min(limit, 100))
    fetch_limit = limit * 3

    items: list[ServerActivityItem] = []

    service_ids = list(db.scalars(select(Service.id).where(Service.server_id == server_id)))
    if service_ids:
        service_names = {s.id: s.name for s in db.scalars(select(Service).where(Service.id.in_(service_ids)))}
        action_logs = db.scalars(
            select(ServiceActionLog)
            .where(ServiceActionLog.service_id.in_(service_ids))
            .order_by(ServiceActionLog.started_at.desc().nullslast())
            .limit(fetch_limit)
        )
        for log in action_logs:
            if log.started_at is None:
                continue
            items.append(
                ServerActivityItem(
                    kind="service_action",
                    occurred_at=log.started_at,
                    title=f"{log.action.value.replace('_', ' ').capitalize()} de {service_names.get(log.service_id, 'servicio')}",
                    detail=log.output,
                    status=log.status.value,
                )
            )

    notifications = db.scalars(
        select(InAppNotification)
        .where(InAppNotification.entity_type == "server", InAppNotification.entity_id == str(server_id))
        .order_by(InAppNotification.created_at.desc())
        .limit(fetch_limit * 5)
    )
    seen: set[tuple] = set()
    for notif in notifications:
        key = (notif.title, notif.message, notif.created_at)
        if key in seen:
            continue
        seen.add(key)
        items.append(
            ServerActivityItem(
                kind="notification",
                occurred_at=notif.created_at,
                title=notif.title,
                detail=notif.message,
                status=notif.severity.value,
            )
        )

    items.sort(key=lambda i: i.occurred_at, reverse=True)
    items = _collapse_connectivity_flaps(items)
    return items[:limit]


@router.delete("/{server_id}", status_code=status.HTTP_204_NO_CONTENT, dependencies=[Depends(require_superuser)])
def delete_server(
    server_id: uuid.UUID,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    site_ids: list[uuid.UUID] | None = Depends(get_visible_site_ids),
) -> None:
    server = db.get(Server, server_id)
    if server is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Servidor no encontrado")
    _ensure_visible(server, site_ids)
    deleted_hostname = server.hostname
    db.delete(server)
    db.commit()
    log_action(
        db, current_user, "server.deleted", "server", server_id, details={"hostname": deleted_hostname}, request=request
    )
