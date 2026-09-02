"""Notifies IT staff about operational incidents (service failures/stops/restarts,
backup/restore/deployment failures, server agent connectivity) both in-app and by
email — routed to the site whose infrastructure is affected.

Recipients = every active superuser (central Coordinación de Informática always
sees everything) + every active non-superuser user assigned to the affected site
who holds servers.manage or services.manage (i.e., the site's own IT staff).
"""

import asyncio
import json
import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import user_has_permission
from app.core.security import decrypt_secret
from app.models.identity import User
from app.models.infrastructure import Server, Site
from app.models.monitoring import (
    InAppNotification,
    NotificationChannel,
    NotificationChannelType,
    NotificationLog,
    NotificationStatus,
)
from app.services.audit import log_action
from app.services.email_templates import render_incident_email
from app.services.maintenance_windows import find_active_window
from app.services.notification_senders import send_email


def site_id_for_server(db: Session, server_id: uuid.UUID | None) -> uuid.UUID | None:
    if server_id is None:
        return None
    server = db.get(Server, server_id)
    return server.site_id if server is not None else None


def resolve_incident_recipients(db: Session, site_id: uuid.UUID | None) -> list[User]:
    recipients: dict = {}

    for user in db.scalars(select(User).where(User.is_active.is_(True), User.is_superuser.is_(True))):
        recipients[user.id] = user

    if site_id is not None:
        site_candidates = db.scalars(
            select(User).where(
                User.is_active.is_(True),
                User.is_superuser.is_(False),
                User.sites.any(Site.id == site_id),
            )
        )
        for user in site_candidates:
            if user.id in recipients:
                continue
            if user_has_permission(db, user, "servers.manage") or user_has_permission(db, user, "services.manage"):
                recipients[user.id] = user

    return list(recipients.values())


async def notify_incident(
    db: Session,
    *,
    site_id: uuid.UUID | None,
    severity: str,
    title: str,
    message: str,
    entity_type: str,
    entity_id: uuid.UUID | str | None,
    email: bool = False,
    server_id: uuid.UUID | None = None,
) -> None:
    """In-app notification always goes out (feeds the bell + the critical-alert banner).
    Email is opt-in per call site — by policy, only the two connectivity events (agent
    disconnected / reconnected) pass email=True; everything else (threshold breaches,
    service/backup/deployment failures) is in-app only, so a técnico's inbox isn't
    flooded with things that resolve themselves or are better triaged inside the app.

    server_id, when passed, is checked against active MaintenanceWindow rows (server- or
    site-scoped) — if the server is under a planned window right now, this call is a
    no-op (no in-app row, no email) regardless of `email`. AlertEvent rows themselves are
    unaffected — see app.services.metric_thresholds — so history stays accurate, only the
    notification is silenced. No caller currently omits server_id when it has one; a
    caller that legitimately has no single server (a future global-scope alert) simply
    never gets suppressed, which is the correct default."""
    if server_id is not None and find_active_window(db, server_id=server_id, site_id=site_id) is not None:
        log_action(
            db, None, "notification.suppressed_maintenance", entity_type, entity_id,
            details={"titulo": title, "servidor_id": str(server_id)},
        )
        return

    recipients = resolve_incident_recipients(db, site_id)
    if not recipients:
        return

    for user in recipients:
        db.add(
            InAppNotification(
                recipient_id=user.id,
                severity=severity,
                title=title,
                message=message,
                entity_type=entity_type,
                entity_id=str(entity_id) if entity_id is not None else None,
            )
        )
    db.commit()

    if not email:
        return

    channel = db.scalar(
        select(NotificationChannel).where(
            NotificationChannel.type == NotificationChannelType.email,
            NotificationChannel.enabled.is_(True),
        )
    )
    channel_id = channel.id if channel is not None else None
    config = json.loads(decrypt_secret(channel.config_encrypted)) if channel is not None and channel.config_encrypted else {}
    # Nothing left to read from the DB past this point — commit now (closing out the
    # transaction opened by the SELECT above) instead of after the send loop below, so the
    # session doesn't sit idle-in-transaction across the blocking SMTP sends, one per
    # recipient, each bounded at send_email's own 15s timeout.
    db.commit()
    if channel_id is None:
        return

    html = render_incident_email(title, message, severity)
    subject = f"CITI Platform: {title}"

    for user in recipients:
        if not user.email:
            # Some accounts (e.g. imported from an external roster) are created without an
            # email yet — they still see the in-app notification above, just not this one.
            continue
        success, error = await asyncio.to_thread(send_email, config, user.email, message, subject, html)
        db.add(
            NotificationLog(
                channel_id=channel_id,
                sent_at=datetime.now(timezone.utc),
                status=NotificationStatus.sent if success else NotificationStatus.failed,
                error_message=error,
            )
        )
    db.commit()
