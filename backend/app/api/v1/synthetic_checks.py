import uuid

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session, aliased

from app.api.deps import get_current_user, get_visible_site_ids, require_permission
from app.core.database import get_db
from app.models.infrastructure import Server
from app.models.monitoring import SyntheticCheckResult
from app.models.systems import Service
from app.schemas.synthetic_check import SyntheticCheckResultRead, SyntheticCheckSummary
from app.services.synthetic_checks import compute_check_summaries, run_all_checks

router = APIRouter(prefix="/synthetic-checks", tags=["synthetic-checks"], dependencies=[Depends(get_current_user)])


def _latest_results(
    db: Session, site_ids: list[uuid.UUID] | None, service_id: uuid.UUID | None = None
) -> list[SyntheticCheckResultRead]:
    """One row per (service, prober) pair — its most recent check — for the status grid.
    Visibility follows the sede of the server that HOSTS the service, not the prober's
    sede (a técnico cares about their own systems' reachability, checked from anywhere)."""
    owner_server = aliased(Server)
    query = (
        select(SyntheticCheckResult, Server.hostname, owner_server.site_id)
        .join(Service, Service.id == SyntheticCheckResult.service_id)
        .outerjoin(Server, Server.id == SyntheticCheckResult.prober_server_id)
        .outerjoin(owner_server, owner_server.id == Service.server_id)
        .distinct(SyntheticCheckResult.service_id, SyntheticCheckResult.prober_server_id)
        .order_by(
            SyntheticCheckResult.service_id, SyntheticCheckResult.prober_server_id, SyntheticCheckResult.checked_at.desc()
        )
    )
    if service_id is not None:
        query = query.where(SyntheticCheckResult.service_id == service_id)
    if site_ids is not None:
        query = query.where(owner_server.site_id.in_(site_ids))

    return [
        SyntheticCheckResultRead(
            id=row.id,
            service_id=row.service_id,
            prober_server_id=row.prober_server_id,
            prober_hostname=hostname,
            success=row.success,
            status_code=row.status_code,
            latency_ms=row.latency_ms,
            error_message=row.error_message,
            checked_at=row.checked_at,
        )
        for row, hostname, _ in db.execute(query)
    ]


@router.get("/results", response_model=list[SyntheticCheckResultRead])
def list_synthetic_check_results(
    db: Session = Depends(get_db), site_ids: list[uuid.UUID] | None = Depends(get_visible_site_ids)
) -> list[SyntheticCheckResultRead]:
    return _latest_results(db, site_ids)


@router.get("/summary", response_model=list[SyntheticCheckSummary])
def get_synthetic_check_summary(
    db: Session = Depends(get_db), site_ids: list[uuid.UUID] | None = Depends(get_visible_site_ids)
) -> list[SyntheticCheckSummary]:
    return compute_check_summaries(db, site_ids)


@router.post(
    "/run", response_model=list[SyntheticCheckResultRead], dependencies=[Depends(require_permission("services.manage"))]
)
async def trigger_synthetic_checks(
    service_id: uuid.UUID | None = None,
    db: Session = Depends(get_db),
    site_ids: list[uuid.UUID] | None = Depends(get_visible_site_ids),
) -> list[SyntheticCheckResultRead]:
    await run_all_checks(db, service_id=service_id)
    return _latest_results(db, site_ids, service_id=service_id)
