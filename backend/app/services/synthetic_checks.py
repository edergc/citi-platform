"""Multi-site synthetic HTTP reachability checks — the agent-per-service model can't see
whether a system is actually reachable from OTHER sedes, only from the server hosting it.
Agents already deployed across ~24 servers/26 sedes double as Datadog-style "private
locations": a probe agent does an HTTP GET against a service's health_check_url and
reports back. See the agent's "http_check" command handler (agent/citi_agent.py).

No separate "check config" table — the active check set is simply every Service with
health_check_url set, times every Server with is_synthetic_probe=True whose Agent is
currently connected.
"""

import asyncio
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session, aliased

from app.core.agent_hub import hub
from app.models.infrastructure import Server, Site
from app.models.monitoring import SyntheticCheckResult
from app.models.systems import Service, System
from app.schemas.synthetic_check import SyntheticCheckSummary, SyntheticOverallStatus, SyntheticProberStatus
from app.services.incident_notifier import notify_incident

HTTP_CHECK_TIMEOUT_SECONDS = 15
UPTIME_WINDOW_DAYS = 7


async def _run_one_check(service: Service, prober: Server) -> dict:
    check_id = uuid.uuid4()
    future = hub.create_pending_result(check_id)
    dispatched = await hub.send_command(
        prober.id, {"type": "http_check", "check_id": str(check_id), "url": service.health_check_url}
    )
    if not dispatched:
        hub.discard_pending_result(check_id)
        return {
            "success": False, "status_code": None, "latency_ms": None,
            "error": "El Agente CITI de la sonda no está conectado.",
        }
    try:
        result = await asyncio.wait_for(future, timeout=HTTP_CHECK_TIMEOUT_SECONDS)
    except asyncio.TimeoutError:
        hub.discard_pending_result(check_id)
        return {
            "success": False, "status_code": None, "latency_ms": None,
            "error": "Tiempo de espera agotado esperando respuesta de la sonda.",
        }
    return {
        "success": bool(result.get("success")),
        "status_code": result.get("status_code"),
        "latency_ms": result.get("latency_ms"),
        "error": result.get("error"),
    }


async def run_all_checks(db: Session, *, service_id: uuid.UUID | None = None) -> list[SyntheticCheckResult]:
    """Runs every active check once. Pass service_id to scope a manual "Verificar ahora"
    to a single service instead of the whole fleet."""
    query = select(Service).where(Service.health_check_url.isnot(None))
    if service_id is not None:
        query = query.where(Service.id == service_id)
    services = list(db.scalars(query))
    probers = [s for s in db.scalars(select(Server).where(Server.is_synthetic_probe.is_(True))) if hub.is_connected(s.id)]
    if not services or not probers:
        return []

    pairs = [(service, prober) for service in services for prober in probers]
    outcomes = await asyncio.gather(*(_run_one_check(service, prober) for service, prober in pairs))

    results: list[SyntheticCheckResult] = []
    now = datetime.now(timezone.utc)
    for (service, prober), outcome in zip(pairs, outcomes):
        previous = db.scalar(
            select(SyntheticCheckResult)
            .where(SyntheticCheckResult.service_id == service.id, SyntheticCheckResult.prober_server_id == prober.id)
            .order_by(SyntheticCheckResult.checked_at.desc())
            .limit(1)
        )
        row = SyntheticCheckResult(
            service_id=service.id,
            prober_server_id=prober.id,
            success=outcome["success"],
            status_code=outcome["status_code"],
            latency_ms=outcome["latency_ms"],
            error_message=outcome["error"],
            checked_at=now,
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        results.append(row)

        # Only notify on a success -> failure transition, not every cycle it stays down —
        # same "don't repeat the same alarm" spirit as AlertRule's cooldown.
        if not outcome["success"] and (previous is None or previous.success):
            reason = outcome["error"] or (f"código {outcome['status_code']}" if outcome["status_code"] else "sin respuesta")
            await notify_incident(
                db,
                site_id=service.server.site_id if service.server else None,
                severity="warning",
                title=f"Inalcanzable desde {prober.hostname}: {service.name}",
                message=f"El chequeo sintético de '{service.name}' falló desde el servidor '{prober.hostname}': {reason}",
                entity_type="synthetic_check",
                entity_id=row.id,
                server_id=service.server_id,
            )

    return results


def compute_check_summaries(
    db: Session, site_ids: list[uuid.UUID] | None, *, window_days: int = UPTIME_WINDOW_DAYS
) -> list[SyntheticCheckSummary]:
    """One row per monitored Service — current status per prober plus a rolling uptime %,
    the Datadog-Synthetics-style "one page, every check, at a glance" view (app/pages
    /sinteticos on the frontend). Two queries per call regardless of fleet size: a
    windowed success-rate aggregate and a DISTINCT ON "latest per pair" — both already
    proven patterns (app.services.problems, app.api.v1.maintenance_windows)."""
    since = datetime.now(timezone.utc) - timedelta(days=window_days)

    services_query = (
        select(Service, System.name, Server.hostname, Server.site_id, Site.name)
        .join(System, System.id == Service.system_id)
        .outerjoin(Server, Server.id == Service.server_id)
        .outerjoin(Site, Site.id == Server.site_id)
        .where(Service.health_check_url.isnot(None))
    )
    if site_ids is not None:
        services_query = services_query.where(Service.server_id.isnot(None), Server.site_id.in_(site_ids))
    service_rows = list(db.execute(services_query))
    if not service_rows:
        return []
    service_ids = [row[0].id for row in service_rows]

    agg_query = (
        select(
            SyntheticCheckResult.service_id,
            SyntheticCheckResult.prober_server_id,
            func.count().label("total"),
            func.sum(case((SyntheticCheckResult.success.is_(True), 1), else_=0)).label("successes"),
            func.avg(SyntheticCheckResult.latency_ms).label("avg_latency"),
        )
        .where(SyntheticCheckResult.service_id.in_(service_ids), SyntheticCheckResult.checked_at >= since)
        .group_by(SyntheticCheckResult.service_id, SyntheticCheckResult.prober_server_id)
    )
    agg_by_pair = {(row.service_id, row.prober_server_id): row for row in db.execute(agg_query)}

    prober = aliased(Server)
    latest_query = (
        select(SyntheticCheckResult, prober.hostname)
        .outerjoin(prober, prober.id == SyntheticCheckResult.prober_server_id)
        .where(SyntheticCheckResult.service_id.in_(service_ids))
        .distinct(SyntheticCheckResult.service_id, SyntheticCheckResult.prober_server_id)
        .order_by(
            SyntheticCheckResult.service_id, SyntheticCheckResult.prober_server_id, SyntheticCheckResult.checked_at.desc()
        )
    )
    latest_by_pair: dict[tuple, tuple] = {}
    for result, prober_hostname in db.execute(latest_query):
        latest_by_pair[(result.service_id, result.prober_server_id)] = (result, prober_hostname)

    summaries: list[SyntheticCheckSummary] = []
    for service, system_name, hostname, server_site_id, site_name in service_rows:
        probers: list[SyntheticProberStatus] = []
        total_successes = 0
        total_checks = 0
        latencies: list[float] = []
        for key, (result, prober_hostname) in latest_by_pair.items():
            if key[0] != service.id:
                continue
            agg = agg_by_pair.get(key)
            pair_uptime = round(100 * agg.successes / agg.total, 1) if agg and agg.total else None
            if agg:
                total_successes += agg.successes
                total_checks += agg.total
                if agg.avg_latency is not None:
                    latencies.append(agg.avg_latency)
            probers.append(
                SyntheticProberStatus(
                    prober_server_id=result.prober_server_id,
                    prober_hostname=prober_hostname,
                    success=result.success,
                    status_code=result.status_code,
                    latency_ms=result.latency_ms,
                    error_message=result.error_message,
                    checked_at=result.checked_at,
                    uptime_percent=pair_uptime,
                )
            )
        probers.sort(key=lambda p: p.prober_hostname or "")

        overall_status: SyntheticOverallStatus
        if not probers:
            overall_status = "unknown"
        elif all(p.success for p in probers):
            overall_status = "up"
        elif all(not p.success for p in probers):
            overall_status = "down"
        else:
            overall_status = "degraded"

        summaries.append(
            SyntheticCheckSummary(
                service_id=service.id,
                service_name=service.name,
                system_id=service.system_id,
                system_name=system_name,
                health_check_url=service.health_check_url,
                server_id=service.server_id,
                hostname=hostname,
                site_id=server_site_id,
                site_name=site_name,
                overall_status=overall_status,
                uptime_percent=round(100 * total_successes / total_checks, 1) if total_checks else None,
                avg_latency_ms=round(sum(latencies) / len(latencies), 1) if latencies else None,
                probers=probers,
            )
        )

    _STATUS_RANK = {"down": 0, "degraded": 1, "unknown": 2, "up": 3}
    summaries.sort(key=lambda s: (_STATUS_RANK[s.overall_status], s.service_name))
    return summaries
