"""In-app view of the weekly rollup (see app.services.weekly_report) — email is the primary
channel, but most técnicos don't have a working email/Telegram, so this is the reliable
fallback: the same data, viewable directly in the app.
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_visible_site_ids
from app.core.database import get_db
from app.models.infrastructure import Site
from app.schemas.report import WeeklyReportRead
from app.services.weekly_report import generate_weekly_report

router = APIRouter(prefix="/reports", tags=["reports"], dependencies=[Depends(get_current_user)])


@router.get("/weekly", response_model=list[WeeklyReportRead])
def get_weekly_reports(
    site_id: uuid.UUID | None = None,
    db: Session = Depends(get_db),
    site_ids: list[uuid.UUID] | None = Depends(get_visible_site_ids),
) -> list[dict]:
    if site_ids is None:
        # Superuser: global rollup by default, or one specific site via ?site_id=.
        if site_id is not None:
            site = db.get(Site, site_id)
            if site is None:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sede no encontrada")
            return [generate_weekly_report(db, site.id)]
        return [generate_weekly_report(db, None)]

    # Site-scoped user: their own sede(s), regardless of any site_id query param.
    sites = list(db.scalars(select(Site).where(Site.id.in_(site_ids)).order_by(Site.name)))
    return [generate_weekly_report(db, s.id) for s in sites]
