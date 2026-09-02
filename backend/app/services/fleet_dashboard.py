"""Fleet-wide aggregate analysis for the admin-only Dashboards page — cross-site
comparisons a técnico shouldn't see (see require_superuser gate on the endpoint), built
entirely from data the app already collects: no new metrics, no new source of truth.
"""

from collections import defaultdict
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.models.infrastructure import Server, Site
from app.models.monitoring import AlertEvent, AlertEventStatus, AlertRule, MaintenanceScope, MaintenanceWindow
from app.schemas.dashboard import (
    AlertTrendPoint,
    FleetDashboard,
    MaintenanceFleetItem,
    MaintenanceSummary,
    OsComparison,
    SiteRanking,
    TopOffender,
)
from app.services.maintenance_windows import list_active_windows, resolve_scope
from app.services.network_path import compute_fleet_network_path
from app.services.server_health import compute_health_map
from app.services.server_uptime import compute_uptime_summary

UPTIME_WINDOW_DAYS = 30
ALERT_TREND_WEEKS = 12
TOP_N = 5


def _avg(values: list[float]) -> float | None:
    return round(sum(values) / len(values), 1) if values else None


def compute_fleet_dashboard(db: Session) -> FleetDashboard:
    servers = list(db.scalars(select(Server).options(selectinload(Server.agent))))
    sites = {s.id: s for s in db.scalars(select(Site))}
    health_map = compute_health_map(db, servers)

    active_windows = list_active_windows(db)
    active_server_ids = {w.scope_id for w in active_windows if w.scope_type == MaintenanceScope.server}
    active_site_ids = {w.scope_id for w in active_windows if w.scope_type == MaintenanceScope.site}

    open_alerts_by_server: dict = defaultdict(int)
    for server_id, count in db.execute(
        select(AlertEvent.server_id, func.count())
        .where(AlertEvent.status == AlertEventStatus.open, AlertEvent.server_id.isnot(None))
        .group_by(AlertEvent.server_id)
    ):
        open_alerts_by_server[server_id] = count

    recent_alerts_by_server: dict = defaultdict(int)
    since_30d = datetime.now(timezone.utc) - timedelta(days=30)
    for server_id, count in db.execute(
        select(AlertEvent.server_id, func.count())
        .where(AlertEvent.server_id.isnot(None), AlertEvent.triggered_at >= since_30d)
        .group_by(AlertEvent.server_id)
    ):
        recent_alerts_by_server[server_id] = count

    # Only servers that have actually been enrolled at least once (server.agent is not
    # None) get an uptime figure — compute_uptime_summary's fallback treats "no
    # connectivity history at all" as 0% for the whole window, which is correct for a
    # server that's genuinely been down since before the window, but wrong to lump in
    # here with servers that were simply never given an agent (most of the bulk-imported
    # fleet). Averaging those in would make "uptime" measure onboarding coverage instead
    # of actual reliability.
    uptime_by_server: dict = {}
    for server in servers:
        if server.agent is None:
            continue
        summary = compute_uptime_summary(db, server, UPTIME_WINDOW_DAYS)
        uptime_by_server[server.id] = summary.uptime_percent

    # Reuses the same fleet-wide network-path summary the /network overview page
    # already computes — no new data source, just a different aggregation of it.
    network_score_by_server: dict = {
        row.server_id: row.quality_score for row in compute_fleet_network_path(db, None) if row.quality_score is not None
    }

    # --- OS comparison ---
    by_os: dict = defaultdict(list)
    for server in servers:
        by_os[server.os_type.value].append(server)

    os_comparison = []
    for os_type, group in sorted(by_os.items()):
        healths = [health_map[s.id].status for s in group]
        cpu_values = [s.agent.cpu_percent for s in group if s.agent is not None and s.agent.cpu_percent is not None]
        ram_values = [s.agent.ram_percent for s in group if s.agent is not None and s.agent.ram_percent is not None]
        uptime_values = [uptime_by_server[s.id] for s in group if uptime_by_server.get(s.id) is not None]
        os_comparison.append(
            OsComparison(
                os_type=os_type,
                server_count=len(group),
                ok_count=sum(1 for h in healths if h == "ok"),
                warning_count=sum(1 for h in healths if h == "warning"),
                critical_count=sum(1 for h in healths if h == "critical"),
                avg_cpu_percent=_avg(cpu_values),
                avg_ram_percent=_avg(ram_values),
                avg_uptime_percent=_avg(uptime_values),
            )
        )

    # --- Site ranking ---
    by_site: dict = defaultdict(list)
    for server in servers:
        if server.site_id is not None:
            by_site[server.site_id].append(server)

    site_ranking = []
    for site_id, group in by_site.items():
        site = sites.get(site_id)
        if site is None:
            continue
        healths = [health_map[s.id].status for s in group]
        cpu_values = [s.agent.cpu_percent for s in group if s.agent is not None and s.agent.cpu_percent is not None]
        ram_values = [s.agent.ram_percent for s in group if s.agent is not None and s.agent.ram_percent is not None]
        uptime_values = [uptime_by_server[s.id] for s in group if uptime_by_server.get(s.id) is not None]
        network_score_values = [network_score_by_server[s.id] for s in group if network_score_by_server.get(s.id) is not None]
        servers_in_maintenance = sum(
            1 for s in group if s.id in active_server_ids or site_id in active_site_ids
        )
        site_ranking.append(
            SiteRanking(
                site_id=site_id,
                site_name=site.name,
                server_count=len(group),
                ok_count=sum(1 for h in healths if h == "ok"),
                warning_count=sum(1 for h in healths if h == "warning"),
                critical_count=sum(1 for h in healths if h == "critical"),
                avg_cpu_percent=_avg(cpu_values),
                avg_ram_percent=_avg(ram_values),
                avg_uptime_percent=_avg(uptime_values),
                avg_network_score=_avg(network_score_values),
                open_alerts=sum(open_alerts_by_server.get(s.id, 0) for s in group),
                servers_in_maintenance=servers_in_maintenance,
            )
        )
    site_ranking.sort(key=lambda r: (r.avg_uptime_percent if r.avg_uptime_percent is not None else 101))

    # --- Alert trend, last N weeks ---
    since_trend = datetime.now(timezone.utc) - timedelta(weeks=ALERT_TREND_WEEKS)
    trend_rows = db.execute(
        select(
            func.date_trunc("week", AlertEvent.triggered_at).label("week_start"),
            AlertRule.severity,
            func.count(),
        )
        .join(AlertRule, AlertRule.id == AlertEvent.alert_rule_id)
        .where(AlertEvent.triggered_at >= since_trend)
        .group_by("week_start", AlertRule.severity)
        .order_by("week_start")
    ).all()
    trend_by_week: dict = defaultdict(lambda: {"critical": 0, "warning": 0, "info": 0})
    for week_start, severity, count in trend_rows:
        trend_by_week[week_start.date()][severity.value] = count
    alert_trend = [
        AlertTrendPoint(week_start=week, critical=counts["critical"], warning=counts["warning"], info=counts["info"])
        for week, counts in sorted(trend_by_week.items())
    ]

    # --- Top offenders ---
    def _offender(server: Server, value: float) -> TopOffender:
        site = sites.get(server.site_id) if server.site_id else None
        return TopOffender(server_id=server.id, hostname=server.hostname, site_name=site.name if site else None, value=value)

    worst_uptime = sorted(
        (_offender(s, uptime_by_server[s.id]) for s in servers if uptime_by_server.get(s.id) is not None),
        key=lambda o: o.value,
    )[:TOP_N]

    most_alerts = sorted(
        (_offender(s, recent_alerts_by_server[s.id]) for s in servers if recent_alerts_by_server.get(s.id)),
        key=lambda o: -o.value,
    )[:TOP_N]

    highest_cpu = sorted(
        (_offender(s, s.agent.cpu_percent) for s in servers if s.agent is not None and s.agent.cpu_percent is not None),
        key=lambda o: -o.value,
    )[:TOP_N]

    highest_ram = sorted(
        (_offender(s, s.agent.ram_percent) for s in servers if s.agent is not None and s.agent.ram_percent is not None),
        key=lambda o: -o.value,
    )[:TOP_N]

    worst_network = sorted(
        (_offender(s, network_score_by_server[s.id]) for s in servers if network_score_by_server.get(s.id) is not None),
        key=lambda o: o.value,
    )[:TOP_N]

    # --- Maintenance ---
    scheduled_count = db.scalar(
        select(func.count()).select_from(MaintenanceWindow).where(
            MaintenanceWindow.cancelled_at.is_(None), MaintenanceWindow.starts_at > datetime.now(timezone.utc)
        )
    )
    # Soonest-to-end first — the ones a dashboard viewer most needs to know are about to
    # lift (and stop suppressing notifications), not the ones that just started.
    soonest_active = sorted(active_windows, key=lambda w: w.ends_at)[:TOP_N]
    maintenance = MaintenanceSummary(
        active_count=len(active_windows),
        scheduled_count=scheduled_count or 0,
        active=[
            MaintenanceFleetItem(
                id=w.id,
                scope_type=w.scope_type,
                scope_label=resolve_scope(db, w.scope_type, w.scope_id)[0],
                reason=w.reason,
                starts_at=w.starts_at,
                ends_at=w.ends_at,
            )
            for w in soonest_active
        ],
    )

    return FleetDashboard(
        os_comparison=os_comparison,
        site_ranking=site_ranking,
        alert_trend=alert_trend,
        worst_uptime=worst_uptime,
        most_alerts=most_alerts,
        highest_cpu=highest_cpu,
        highest_ram=highest_ram,
        worst_network=worst_network,
        maintenance=maintenance,
    )
