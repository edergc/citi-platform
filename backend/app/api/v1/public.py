from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.database import get_db
from app.models.infrastructure import Agent, Server, Site
from app.models.systems import ServiceStatus, System, SystemStatus
from app.schemas.public import PublicServerStatus, PublicSystemStatus

router = APIRouter(prefix="/public", tags=["public"])


def _aggregate_status(statuses: list[ServiceStatus]) -> str:
    if not statuses:
        return "unknown"
    if all(s == ServiceStatus.stopped for s in statuses):
        return "down"
    if any(s in (ServiceStatus.stopped, ServiceStatus.degraded) for s in statuses):
        return "degraded"
    return "operational"


@router.get("/status", response_model=list[PublicSystemStatus])
def public_status(db: Session = Depends(get_db)) -> list[PublicSystemStatus]:
    systems = db.scalars(
        select(System)
        .where(System.status != SystemStatus.retired)
        .options(selectinload(System.services))
        .order_by(System.name)
    ).all()

    result = []
    for system in systems:
        statuses = [service.status for service in system.services]
        checked_ats = [service.last_checked_at for service in system.services if service.last_checked_at is not None]
        result.append(
            PublicSystemStatus(
                name=system.name,
                category=system.category,
                status=_aggregate_status(statuses),
                last_checked_at=max(checked_ats) if checked_ats else None,
            )
        )
    return result


@router.get("/servers", response_model=list[PublicServerStatus])
def public_servers(db: Session = Depends(get_db)) -> list[PublicServerStatus]:
    """Deliberately minimal — hostname, sede and connectivity only. No IP, specs, or any
    other internal detail: this endpoint has no authentication."""
    rows = db.execute(
        select(Server.hostname, Site.name, Server.status, Agent.last_heartbeat_at)
        .outerjoin(Site, Site.id == Server.site_id)
        .outerjoin(Agent, Agent.server_id == Server.id)
        .order_by(Site.name.nulls_last(), Server.hostname)
    )
    return [
        PublicServerStatus(hostname=hostname, site_name=site_name, status=status.value, last_heartbeat_at=last_heartbeat_at)
        for hostname, site_name, status, last_heartbeat_at in rows
    ]
