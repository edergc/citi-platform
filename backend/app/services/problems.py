"""Aggregates "what's currently wrong" across the fleet into one list, for the unified
Problems dashboard (app.api.v1.problems) — the Checkmk-style single table that replaces
having to check Alertas/Servidores/Sistemas separately. Five sources, each answering
"is this thing broken right now", not a historical log:

- open AlertEvent rows (threshold breaches)
- servers currently offline/degraded
- services currently degraded
- the most recent backup/deployment run per job/system, when it failed (clears itself
  automatically the moment a later run succeeds, since only the latest is ever looked at)
- the most recent synthetic HTTP check per (service, prober site), when unreachable
  (same self-clearing behavior as backup/deploy above)
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import desc, select
from sqlalchemy.orm import Session, aliased

from app.models.backups import BackupJob, BackupRun, RunStatus
from app.models.infrastructure import Server, ServerStatus, Site
from app.models.monitoring import AlertEvent, AlertEventStatus, AlertRule, AlertSeverity, SyntheticCheckResult
from app.models.systems import Service, ServiceStatus, System
from app.models.versions import Deployment, DeploymentStatus
from app.schemas.problem import ProblemRow
from app.services.maintenance_windows import bulk_maintenance_windows, was_under_maintenance


def _alert_problems(db: Session, site_ids: list[uuid.UUID] | None) -> list[ProblemRow]:
    query = (
        select(AlertEvent, AlertRule, Server.hostname, Server.site_id, Site.name)
        .join(AlertRule, AlertRule.id == AlertEvent.alert_rule_id)
        .outerjoin(Server, Server.id == AlertEvent.server_id)
        .outerjoin(Site, Site.id == Server.site_id)
        .where(AlertEvent.status == AlertEventStatus.open)
    )
    if site_ids is not None:
        query = query.where(AlertEvent.server_id.isnot(None), Server.site_id.in_(site_ids))

    rows: list[ProblemRow] = []
    for event, rule, hostname, server_site_id, site_name in db.execute(query):
        detail_parts = [rule.metric]
        if event.value is not None:
            detail_parts.append(f"{event.value:.1f}")
        rows.append(
            ProblemRow(
                id=f"alert:{event.id}",
                kind="alert",
                severity=rule.severity,
                title=rule.name,
                detail=" · ".join(detail_parts),
                server_id=event.server_id,
                hostname=hostname,
                site_id=server_site_id,
                site_name=site_name,
                system_id=None,
                system_name=None,
                occurred_at=event.triggered_at,
                during_maintenance=False,
                alert_event_id=event.id,
                acknowledged_at=event.acknowledged_at,
            )
        )
    return rows


def _server_problems(db: Session, site_ids: list[uuid.UUID] | None) -> list[ProblemRow]:
    query = select(Server, Site.name).outerjoin(Site, Site.id == Server.site_id).where(
        Server.status.in_((ServerStatus.offline, ServerStatus.degraded))
    )
    if site_ids is not None:
        query = query.where(Server.site_id.in_(site_ids))

    rows: list[ProblemRow] = []
    for server, site_name in db.execute(query):
        offline = server.status == ServerStatus.offline
        rows.append(
            ProblemRow(
                id=f"server:{server.id}",
                kind="server_offline" if offline else "server_degraded",
                severity=AlertSeverity.critical if offline else AlertSeverity.warning,
                title=f"Servidor {'desconectado' if offline else 'degradado'}: {server.hostname}",
                detail=str(server.ip_address) if server.ip_address else None,
                server_id=server.id,
                hostname=server.hostname,
                site_id=server.site_id,
                site_name=site_name,
                system_id=None,
                system_name=None,
                occurred_at=server.updated_at,
                during_maintenance=False,
            )
        )
    return rows


def _service_problems(db: Session, site_ids: list[uuid.UUID] | None) -> list[ProblemRow]:
    query = (
        select(Service, System.name, Server.hostname, Server.site_id, Site.name)
        .join(System, System.id == Service.system_id)
        .outerjoin(Server, Server.id == Service.server_id)
        .outerjoin(Site, Site.id == Server.site_id)
        .where(Service.status == ServiceStatus.degraded)
    )
    if site_ids is not None:
        query = query.where(Service.server_id.isnot(None), Server.site_id.in_(site_ids))

    rows: list[ProblemRow] = []
    for service, system_name, hostname, server_site_id, site_name in db.execute(query):
        rows.append(
            ProblemRow(
                id=f"service:{service.id}",
                kind="service_degraded",
                severity=AlertSeverity.critical,
                title=f"Servicio degradado: {service.name}",
                detail=system_name,
                server_id=service.server_id,
                hostname=hostname,
                site_id=server_site_id,
                site_name=site_name,
                system_id=service.system_id,
                system_name=system_name,
                occurred_at=service.last_checked_at or service.updated_at,
                during_maintenance=False,
            )
        )
    return rows


def _backup_problems(db: Session, site_ids: list[uuid.UUID] | None) -> list[ProblemRow]:
    # DISTINCT ON must apply before any site filter would exclude a job's only/latest
    # run — sites are checked in Python below instead of adding a WHERE that could
    # change which row DISTINCT ON picks as "latest" per job.
    query = (
        select(BackupRun, BackupJob, Service, System, Server, Site)
        .join(BackupJob, BackupJob.id == BackupRun.backup_job_id)
        .join(Service, Service.id == BackupJob.service_id)
        .join(System, System.id == Service.system_id)
        .outerjoin(Server, Server.id == Service.server_id)
        .outerjoin(Site, Site.id == Server.site_id)
        .distinct(BackupRun.backup_job_id)
        .order_by(BackupRun.backup_job_id, desc(BackupRun.started_at))
    )
    rows: list[ProblemRow] = []
    for run, job, service, system, server, site in db.execute(query):
        if run.status != RunStatus.failed:
            continue
        if site_ids is not None and (server is None or server.site_id not in site_ids):
            continue
        rows.append(
            ProblemRow(
                id=f"backup:{job.id}",
                kind="backup_failed",
                severity=AlertSeverity.warning,
                title=f"Backup fallido: {service.name}",
                detail=run.error_message or system.name,
                server_id=server.id if server else None,
                hostname=server.hostname if server else None,
                site_id=site.id if site else None,
                site_name=site.name if site else None,
                system_id=system.id,
                system_name=system.name,
                occurred_at=run.finished_at or run.started_at or datetime.now(timezone.utc),
                during_maintenance=False,
            )
        )
    return rows


def _deploy_problems(db: Session) -> list[ProblemRow]:
    query = (
        select(Deployment, System)
        .join(System, System.id == Deployment.system_id)
        .distinct(Deployment.system_id)
        .order_by(Deployment.system_id, desc(Deployment.started_at))
    )
    rows: list[ProblemRow] = []
    for deployment, system in db.execute(query):
        if deployment.status != DeploymentStatus.failed:
            continue
        rows.append(
            ProblemRow(
                id=f"deploy:{system.id}",
                kind="deploy_failed",
                severity=AlertSeverity.warning,
                title=f"Despliegue fallido: {system.name}",
                detail=deployment.log_output,
                server_id=None,
                hostname=None,
                site_id=None,
                site_name=None,
                system_id=system.id,
                system_name=system.name,
                occurred_at=deployment.finished_at or deployment.started_at or datetime.now(timezone.utc),
                during_maintenance=False,
            )
        )
    return rows


def _synthetic_problems(db: Session, site_ids: list[uuid.UUID] | None) -> list[ProblemRow]:
    prober = aliased(Server)
    # Same DISTINCT ON caveat as backups/deploys above: site filtering happens in Python
    # after picking the latest row per (service, prober) pair, not in the WHERE clause.
    query = (
        select(SyntheticCheckResult, Service, System, Server, Site, prober)
        .join(Service, Service.id == SyntheticCheckResult.service_id)
        .join(System, System.id == Service.system_id)
        .outerjoin(Server, Server.id == Service.server_id)
        .outerjoin(Site, Site.id == Server.site_id)
        .outerjoin(prober, prober.id == SyntheticCheckResult.prober_server_id)
        .distinct(SyntheticCheckResult.service_id, SyntheticCheckResult.prober_server_id)
        .order_by(
            SyntheticCheckResult.service_id, SyntheticCheckResult.prober_server_id, SyntheticCheckResult.checked_at.desc()
        )
    )
    rows: list[ProblemRow] = []
    for result, service, system, owner_server, site, prober_server in db.execute(query):
        if result.success:
            continue
        if site_ids is not None and (owner_server is None or owner_server.site_id not in site_ids):
            continue
        prober_label = prober_server.hostname if prober_server else "sonda eliminada"
        rows.append(
            ProblemRow(
                id=f"synthetic:{result.id}",
                kind="synthetic_failed",
                severity=AlertSeverity.warning,
                title=f"Inalcanzable desde {prober_label}: {service.name}",
                detail=result.error_message or (f"código {result.status_code}" if result.status_code else None),
                server_id=owner_server.id if owner_server else None,
                hostname=owner_server.hostname if owner_server else None,
                site_id=site.id if site else None,
                site_name=site.name if site else None,
                system_id=system.id,
                system_name=system.name,
                occurred_at=result.checked_at,
                during_maintenance=False,
            )
        )
    return rows


_SEVERITY_RANK = {AlertSeverity.critical: 0, AlertSeverity.warning: 1, AlertSeverity.info: 2}


def compute_problems(db: Session, site_ids: list[uuid.UUID] | None) -> list[ProblemRow]:
    rows = _alert_problems(db, site_ids) + _server_problems(db, site_ids) + _service_problems(db, site_ids)
    # Despliegues fallidos son a nivel de Sistema (sin una sola sede clara) — mismo criterio
    # que las reglas de alcance global en list_alert_events: solo visibles sin restricción de sede.
    if site_ids is None:
        rows += _deploy_problems(db)
    rows += _backup_problems(db, site_ids)
    rows += _synthetic_problems(db, site_ids)

    server_ids = {r.server_id for r in rows if r.server_id is not None}
    row_site_ids = {r.site_id for r in rows if r.site_id is not None}
    windows_by_server, windows_by_site = bulk_maintenance_windows(db, server_ids=server_ids, site_ids=row_site_ids)
    now = datetime.now(timezone.utc)
    for row in rows:
        if row.kind in ("backup_failed", "deploy_failed"):
            continue
        row.during_maintenance = was_under_maintenance(
            windows_by_server, windows_by_site, server_id=row.server_id, site_id=row.site_id, at=now
        )

    rows.sort(key=lambda r: (_SEVERITY_RANK[r.severity], -r.occurred_at.timestamp()))
    return rows
