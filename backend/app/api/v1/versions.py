import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_permission
from app.core.database import get_db
from app.models.identity import User
from app.models.systems import System
from app.models.versions import SystemVersion, VersionStatus
from app.schemas.version import SystemVersionCreate, SystemVersionRead
from app.services.audit import log_action

router = APIRouter(tags=["versions"], dependencies=[Depends(get_current_user)])


@router.get("/systems/{system_id}/versions", response_model=list[SystemVersionRead])
def list_versions(system_id: uuid.UUID, db: Session = Depends(get_db)) -> list[SystemVersion]:
    query = select(SystemVersion).where(SystemVersion.system_id == system_id).order_by(SystemVersion.created_at.desc())
    return list(db.scalars(query))


@router.post(
    "/systems/{system_id}/versions",
    response_model=SystemVersionRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission("versions.manage"))],
)
def create_version(
    system_id: uuid.UUID,
    payload: SystemVersionCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> SystemVersion:
    system = db.get(System, system_id)
    if system is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sistema no encontrado")

    # The newly registered version becomes the active one; whatever was active before is now deprecated.
    previous_active = db.scalars(
        select(SystemVersion).where(SystemVersion.system_id == system_id, SystemVersion.status == VersionStatus.active)
    )
    for v in previous_active:
        v.status = VersionStatus.deprecated

    version = SystemVersion(
        system_id=system_id,
        version_number=payload.version_number,
        git_commit_hash=payload.git_commit_hash,
        git_branch=payload.git_branch,
        release_notes=payload.release_notes,
        status=VersionStatus.active,
        released_by_id=current_user.id,
        released_at=datetime.now(timezone.utc),
    )
    db.add(version)
    db.commit()
    db.refresh(version)
    log_action(
        db, current_user, "version.created", "system_version", version.id,
        details={"system_id": str(system_id), "version_number": version.version_number}, request=request,
    )
    return version


@router.post(
    "/versions/{version_id}/rollback",
    response_model=SystemVersionRead,
    dependencies=[Depends(require_permission("versions.manage"))],
)
def rollback_to_version(
    version_id: uuid.UUID, request: Request, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)
) -> SystemVersion:
    """Marks a previous version as active again (bookkeeping only).

    This does not touch any running code — it records that operations rolled back
    to this version. Actually re-deploying the corresponding code/build is the
    Deployment Center's job (Phase 4, later step).
    """
    target = db.get(SystemVersion, version_id)
    if target is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Versión no encontrada")

    currently_active = db.scalars(
        select(SystemVersion).where(SystemVersion.system_id == target.system_id, SystemVersion.status == VersionStatus.active)
    )
    for v in currently_active:
        v.status = VersionStatus.rolled_back

    target.status = VersionStatus.active
    db.commit()
    db.refresh(target)
    log_action(
        db, current_user, "version.rollback_triggered", "system_version", target.id,
        details={"system_id": str(target.system_id), "version_number": target.version_number}, request=request,
    )
    return target
