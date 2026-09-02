"""Reads back the network-path probe history the agent reports on its own timer (see
agent/citi_agent.py's network_path_loop) — this module doesn't do any probing itself,
just formats what's already in server_network_path_history for the API response.
"""

import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.infrastructure import Server, ServerNetworkPathHistory, Site
from app.schemas.network_path import (
    NetworkLatencySparkline,
    NetworkLatencySparklinePoint,
    NetworkPathFleetRow,
    NetworkPathHistory,
    NetworkPathSample,
)


# Below this latency, no penalty at all — a reasonable baseline for round-trips within
# an internal institutional WAN (see the real samples gathered this session: healthy
# servers land at 1-10ms). Loss is weighted 1:1 (real, punishing); latency is capped so
# it alone can't sink the score as hard as real packet loss does.
QUALITY_GOOD_LATENCY_MS = 30.0
QUALITY_LATENCY_DIVISOR = 5.0
QUALITY_MAX_LATENCY_PENALTY = 40.0


def compute_network_quality_score(
    reachable: bool | None, loss_percent: float | None, latency_ms: float | None
) -> int | None:
    """A single 0-100 number summarizing a server's network path to Core, so a técnico
    doesn't have to read Estado + Pérdida + Latencia separately to judge "is this
    fine". None (not 0) when there's no sample yet — 0 is reserved for a real, known
    failure (reachable=False), never for "we don't know"."""
    if reachable is None:
        return None
    if not reachable:
        return 0
    score = 100.0
    if loss_percent is not None:
        score -= min(loss_percent, 100.0)
    if latency_ms is not None and latency_ms > QUALITY_GOOD_LATENCY_MS:
        penalty = min((latency_ms - QUALITY_GOOD_LATENCY_MS) / QUALITY_LATENCY_DIVISOR, QUALITY_MAX_LATENCY_PENALTY)
        score -= penalty
    return round(max(score, 0.0))


def compute_network_path(db: Session, server_id: uuid.UUID, hours: int) -> NetworkPathHistory:
    since = datetime.now(timezone.utc) - timedelta(hours=hours)
    rows = list(
        db.scalars(
            select(ServerNetworkPathHistory)
            .where(
                ServerNetworkPathHistory.server_id == server_id,
                ServerNetworkPathHistory.recorded_at >= since,
            )
            .order_by(ServerNetworkPathHistory.recorded_at)
        )
    )

    samples = [
        NetworkPathSample(
            recorded_at=row.recorded_at,
            target=row.target,
            reachable=row.reachable,
            hops=row.hops,
            quality_score=compute_network_quality_score(
                row.reachable,
                row.hops[-1].get("packet_loss_percent") if row.hops else None,
                row.hops[-1].get("avg_latency_ms") if row.hops else None,
            ),
        )
        for row in rows
    ]
    return NetworkPathHistory(current=samples[-1] if samples else None, samples=samples)


def compute_fleet_network_path(db: Session, site_ids: list[uuid.UUID] | None) -> list[NetworkPathFleetRow]:
    """One row per visible server — the fleet-wide network status board. Servers with
    no ServerNetworkPathHistory row yet (agent not updated to 1.4.0+, or just enrolled)
    still appear, with every field but hostname/site_name left None, so "sin datos" is
    visibly distinct from "no responde" instead of just silently missing."""
    server_query = select(Server)
    if site_ids is not None:
        server_query = server_query.where(Server.site_id.in_(site_ids))
    servers = list(db.scalars(server_query))
    if not servers:
        return []

    sites = {s.id: s for s in db.scalars(select(Site))}

    # Postgres DISTINCT ON: one query for the latest sample per server, instead of a
    # per-server round trip — same performance approach fleet_dashboard.py already
    # uses for other per-server aggregates.
    latest_rows = db.scalars(
        select(ServerNetworkPathHistory)
        .where(ServerNetworkPathHistory.server_id.in_([s.id for s in servers]))
        .distinct(ServerNetworkPathHistory.server_id)
        .order_by(ServerNetworkPathHistory.server_id, ServerNetworkPathHistory.recorded_at.desc())
    )
    latest_by_server = {row.server_id: row for row in latest_rows}

    result: list[NetworkPathFleetRow] = []
    for server in servers:
        site = sites.get(server.site_id) if server.site_id else None
        latest = latest_by_server.get(server.id)
        if latest is None:
            result.append(
                NetworkPathFleetRow(
                    server_id=server.id,
                    hostname=server.hostname,
                    site_id=server.site_id,
                    site_name=site.name if site else None,
                    target=None,
                    reachable=None,
                    hop_count=None,
                    final_latency_ms=None,
                    destination_loss_percent=None,
                    intermediate_max_loss_percent=None,
                    quality_score=None,
                    recorded_at=None,
                )
            )
            continue

        intermediate_hops = latest.hops[:-1]
        intermediate_loss_values = [
            h.get("packet_loss_percent") for h in intermediate_hops if h.get("packet_loss_percent") is not None
        ]
        final_latency_ms = latest.hops[-1].get("avg_latency_ms") if latest.hops else None
        destination_loss_percent = latest.hops[-1].get("packet_loss_percent") if latest.hops else None
        result.append(
            NetworkPathFleetRow(
                server_id=server.id,
                hostname=server.hostname,
                site_id=server.site_id,
                site_name=site.name if site else None,
                target=latest.target,
                reachable=latest.reachable,
                hop_count=len(latest.hops),
                final_latency_ms=final_latency_ms,
                destination_loss_percent=destination_loss_percent,
                intermediate_max_loss_percent=max(intermediate_loss_values) if intermediate_loss_values else None,
                quality_score=compute_network_quality_score(latest.reachable, destination_loss_percent, final_latency_ms),
                recorded_at=latest.recorded_at,
            )
        )
    return result


def compute_network_latency_sparklines(
    db: Session, site_ids: list[uuid.UUID] | None, hours: int
) -> list[NetworkLatencySparkline]:
    """Bulk query for every visible server's recent destination-latency trend, mirroring
    get_server_sparklines' CPU/RAM version — one request instead of one per row."""
    since = datetime.now(timezone.utc) - timedelta(hours=hours)

    server_query = select(Server.id)
    if site_ids is not None:
        server_query = server_query.where(Server.site_id.in_(site_ids))
    visible_ids = set(db.scalars(server_query))
    if not visible_ids:
        return []

    rows = db.scalars(
        select(ServerNetworkPathHistory)
        .where(ServerNetworkPathHistory.server_id.in_(visible_ids), ServerNetworkPathHistory.recorded_at >= since)
        .order_by(ServerNetworkPathHistory.recorded_at)
    )
    by_server: dict[uuid.UUID, list[NetworkLatencySparklinePoint]] = {}
    for row in rows:
        latency_ms = row.hops[-1].get("avg_latency_ms") if row.hops else None
        by_server.setdefault(row.server_id, []).append(
            NetworkLatencySparklinePoint(recorded_at=row.recorded_at, latency_ms=latency_ms)
        )
    return [NetworkLatencySparkline(server_id=server_id, points=points) for server_id, points in by_server.items()]
