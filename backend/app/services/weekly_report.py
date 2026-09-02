"""Weekly accountability rollup: server uptime, alert backlog, and backup health over the
past 7 days — one email per site to that site's técnicos, plus a global summary to
superusers. Complements notify_incident() (real-time, per-event) with a periodic recap so
nothing needs an active incident to be visible; this is what backs the "no me avisaron"
concern the técnico role change was meant to close.
"""

import asyncio
import json
import logging
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import decrypt_secret
from app.models.backups import BackupJob, BackupRun, RunStatus
from app.models.identity import User
from app.models.infrastructure import Server, ServerStatus, Site
from app.models.monitoring import (
    AlertEvent,
    AlertEventStatus,
    AlertRule,
    NotificationChannel,
    NotificationChannelType,
    NotificationLog,
    NotificationStatus,
)
from app.models.systems import Service
from app.services.email_templates import render_weekly_report_email
from app.services.incident_notifier import resolve_incident_recipients
from app.services.notification_senders import send_email

logger = logging.getLogger("citi.scheduler")

REPORT_WINDOW = timedelta(days=7)

# Caps how many rows of each detail list the report carries — a weekly rollup is meant to
# be scannable (in the app and especially in an email); beyond this the counts above still
# tell the whole story, and the individual server/alert/backup pages have the full list.
DETAIL_LIST_LIMIT = 15

# Peru has had no daylight-saving time since 1994, so a fixed UTC-5 offset is correct
# year-round and avoids pulling in zoneinfo/tzdata (not bundled with the Windows Python
# runtime used elsewhere in this project).
LIMA_OFFSET = timezone(timedelta(hours=-5))


def _next_run_at(now_utc: datetime) -> datetime:
    """Next Monday 08:00 Lima time, expressed in UTC."""
    now_lima = now_utc.astimezone(LIMA_OFFSET)
    days_ahead = (7 - now_lima.weekday()) % 7  # datetime.weekday(): Monday == 0
    candidate = now_lima.replace(hour=8, minute=0, second=0, microsecond=0) + timedelta(days=days_ahead)
    if candidate <= now_lima:
        candidate += timedelta(days=7)
    return candidate.astimezone(timezone.utc)


def generate_weekly_report(db: Session, site_id: uuid.UUID | None) -> dict:
    """site_id=None produces the unscoped global summary (for superusers); otherwise the
    report is limited to that site's servers/backups/alerts."""
    now = datetime.now(timezone.utc)
    window_start = now - REPORT_WINDOW

    site_name = db.scalar(select(Site.name).where(Site.id == site_id)) if site_id is not None else None

    server_query = select(Server)
    if site_id is not None:
        server_query = server_query.where(Server.site_id == site_id)
    servers = list(db.scalars(server_query))
    server_ids = [s.id for s in servers]
    servers_online = sum(1 for s in servers if s.status == ServerStatus.online)
    servers_offline = sum(1 for s in servers if s.status != ServerStatus.online)
    offline_servers = [
        {"id": s.id, "hostname": s.hostname, "status": s.status.value}
        for s in servers
        if s.status != ServerStatus.online
    ][:DETAIL_LIST_LIMIT]

    open_alerts_by_severity = {"critical": 0, "warning": 0, "info": 0}
    unacknowledged_open_alerts = 0
    open_alerts: list[dict] = []
    alert_query = (
        select(
            AlertEvent.id,
            AlertEvent.server_id,
            Server.hostname,
            AlertRule.name,
            AlertRule.severity,
            AlertEvent.acknowledged_at,
            AlertEvent.value,
        )
        .join(AlertRule, AlertRule.id == AlertEvent.alert_rule_id)
        .outerjoin(Server, Server.id == AlertEvent.server_id)
        .where(AlertEvent.status == AlertEventStatus.open)
        .order_by(AlertEvent.triggered_at.desc())
    )
    if site_id is not None:
        alert_rows = db.execute(alert_query.where(AlertEvent.server_id.in_(server_ids))) if server_ids else []
    else:
        alert_rows = db.execute(alert_query)
    for event_id, server_id_, hostname, rule_name, severity, acknowledged_at, value in alert_rows:
        open_alerts_by_severity[severity.value] = open_alerts_by_severity.get(severity.value, 0) + 1
        if acknowledged_at is None:
            unacknowledged_open_alerts += 1
        if len(open_alerts) < DETAIL_LIST_LIMIT:
            open_alerts.append(
                {
                    "id": event_id,
                    "hostname": hostname,
                    "rule_name": rule_name,
                    "severity": severity.value,
                    "value": value,
                    "acknowledged": acknowledged_at is not None,
                }
            )

    backup_query = (
        select(BackupRun.id, BackupRun.error_message, BackupRun.started_at, Service.name, BackupJob.type)
        .join(BackupJob, BackupJob.id == BackupRun.backup_job_id)
        .join(Service, Service.id == BackupJob.service_id)
        .where(BackupRun.status == RunStatus.failed, BackupRun.started_at >= window_start)
        .order_by(BackupRun.started_at.desc())
    )
    if site_id is not None:
        backup_query = backup_query.join(Server, Server.id == Service.server_id).where(Server.site_id == site_id)
    backup_rows = list(db.execute(backup_query))
    failed_backups = [
        {
            "id": run_id,
            "service_name": service_name,
            "type": backup_type.value,
            "error_message": error_message,
            "started_at": started_at,
        }
        for run_id, error_message, started_at, service_name, backup_type in backup_rows[:DETAIL_LIST_LIMIT]
    ]

    return {
        "site_id": site_id,
        "site_name": site_name,
        "window_start": window_start,
        "window_end": now,
        "servers_total": len(servers),
        "servers_online": servers_online,
        "servers_offline": servers_offline,
        "offline_servers": offline_servers,
        "open_alerts_by_severity": open_alerts_by_severity,
        "unacknowledged_open_alerts": unacknowledged_open_alerts,
        "open_alerts": open_alerts,
        "backup_failures": len(backup_rows),
        "failed_backups": failed_backups,
    }


async def _send_to(db: Session, channel: NotificationChannel, config: dict, recipients: list[User], report: dict, subject: str) -> None:
    html = render_weekly_report_email(report)
    for user in recipients:
        if not user.email:
            continue
        success, error = await asyncio.to_thread(send_email, config, user.email, subject, subject, html)
        db.add(
            NotificationLog(
                channel_id=channel.id,
                sent_at=datetime.now(timezone.utc),
                status=NotificationStatus.sent if success else NotificationStatus.failed,
                error_message=error,
            )
        )
    db.commit()


async def send_weekly_report(db: Session) -> None:
    channel = db.scalar(
        select(NotificationChannel).where(
            NotificationChannel.type == NotificationChannelType.email,
            NotificationChannel.enabled.is_(True),
        )
    )
    if channel is None:
        logger.info("Reporte semanal: no hay canal de correo habilitado, se omite el envío")
        return
    config = json.loads(decrypt_secret(channel.config_encrypted)) if channel.config_encrypted else {}

    for site in list(db.scalars(select(Site).order_by(Site.name))):
        recipients = [u for u in resolve_incident_recipients(db, site.id) if not u.is_superuser]
        if not recipients:
            continue
        report = generate_weekly_report(db, site.id)
        # Everything needed for this site's send is in local variables now — commit here,
        # before _send_to's blocking SMTP loop, so the session isn't left idle-in-transaction
        # (holding whatever the reads above accumulated) for the duration of the sends.
        db.commit()
        await _send_to(db, channel, config, recipients, report, f"CITI Platform: Reporte semanal — {site.name}")

    superusers = list(
        db.scalars(select(User).where(User.is_active.is_(True), User.is_superuser.is_(True)))
    )
    if superusers:
        report = generate_weekly_report(db, None)
        db.commit()
        await _send_to(db, channel, config, superusers, report, "CITI Platform: Reporte semanal — Resumen global")
