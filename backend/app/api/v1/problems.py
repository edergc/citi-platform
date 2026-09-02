import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_visible_site_ids
from app.core.database import get_db
from app.models.monitoring import AlertSeverity
from app.schemas.problem import ProblemKind, ProblemRow
from app.services.problems import compute_problems

router = APIRouter(prefix="/problems", tags=["problems"], dependencies=[Depends(get_current_user)])


@router.get("", response_model=list[ProblemRow])
def list_problems(
    kind_filter: ProblemKind | None = None,
    severity_filter: AlertSeverity | None = None,
    site_id_filter: uuid.UUID | None = None,
    search: str | None = None,
    limit: int = 200,
    db: Session = Depends(get_db),
    site_ids: list[uuid.UUID] | None = Depends(get_visible_site_ids),
) -> list[ProblemRow]:
    limit = max(1, min(limit, 500))
    rows = compute_problems(db, site_ids)

    if kind_filter is not None:
        rows = [r for r in rows if r.kind == kind_filter]
    if severity_filter is not None:
        rows = [r for r in rows if r.severity == severity_filter]
    if site_id_filter is not None:
        rows = [r for r in rows if r.site_id == site_id_filter]
    if search:
        term = search.strip().lower()
        rows = [
            r for r in rows
            if term in r.title.lower()
            or (r.hostname and term in r.hostname.lower())
            or (r.system_name and term in r.system_name.lower())
        ]

    return rows[:limit]
