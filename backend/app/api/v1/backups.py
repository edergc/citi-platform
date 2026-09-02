import asyncio
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_permission
from app.core.agent_hub import hub
from app.core.database import get_db
from app.core.security import decrypt_secret
from app.models.backups import BackupJob, BackupRun, BackupType, RestoreOperation, RunStatus, TriggerType
from app.models.config import ConfigEntry
from app.models.identity import User
from app.models.systems import Service
from app.schemas.backup import (
    BackupJobCreate,
    BackupJobRead,
    BackupJobUpdate,
    BackupRunPage,
    BackupRunRead,
    RestoreOperationRead,
)
from app.services.audit import diff_changed_fields, log_action
from app.services.incident_notifier import notify_incident, site_id_for_server

router = APIRouter(tags=["backups"], dependencies=[Depends(get_current_user)])

BACKUP_TIMEOUT_SECONDS = 120
RESTORE_TIMEOUT_SECONDS = 120

REQUIRED_DB_KEYS = ("DB_HOST", "DB_PORT", "DB_NAME", "DB_USER", "DB_PASSWORD")


def _get_db_credentials(db: Session, service_id: uuid.UUID) -> dict[str, str]:
    entries = db.scalars(select(ConfigEntry).where(ConfigEntry.service_id == service_id))
    values: dict[str, str] = {}
    for entry in entries:
        if entry.key in REQUIRED_DB_KEYS and entry.value is not None:
            values[entry.key] = decrypt_secret(entry.value) if entry.is_secret else entry.value

    missing = [k for k in REQUIRED_DB_KEYS if k not in values]
    if missing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Faltan credenciales de base de datos para este servicio: {', '.join(missing)}",
        )
    return values


@router.post(
    "/backup-jobs", response_model=BackupJobRead, status_code=status.HTTP_201_CREATED, dependencies=[Depends(require_permission("backups.manage"))]
)
def create_backup_job(
    payload: BackupJobCreate, request: Request, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)
) -> BackupJob:
    service = db.get(Service, payload.service_id)
    if service is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Servicio no encontrado")
    job = BackupJob(**payload.model_dump())
    db.add(job)
    db.commit()
    db.refresh(job)
    log_action(
        db, current_user, "backup_job.created", "backup_job", job.id,
        details={"type": job.type.value, "source_path": job.source_path}, request=request,
    )
    return job


@router.get("/backup-jobs", response_model=list[BackupJobRead])
def list_backup_jobs(service_id: uuid.UUID | None = None, db: Session = Depends(get_db)) -> list[BackupJob]:
    query = select(BackupJob).order_by(BackupJob.created_at.desc())
    if service_id is not None:
        query = query.where(BackupJob.service_id == service_id)
    return list(db.scalars(query))


@router.patch("/backup-jobs/{job_id}", response_model=BackupJobRead, dependencies=[Depends(require_permission("backups.manage"))])
def update_backup_job(
    job_id: uuid.UUID,
    payload: BackupJobUpdate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> BackupJob:
    job = db.get(BackupJob, job_id)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job de respaldo no encontrado")
    data = payload.model_dump(exclude_unset=True)
    changes = diff_changed_fields(job, data)
    for field, value in data.items():
        setattr(job, field, value)
    db.commit()
    db.refresh(job)
    log_action(
        db, current_user, "backup_job.updated", "backup_job", job.id,
        details={"changes": changes} if changes else None, request=request,
    )
    return job


@router.delete("/backup-jobs/{job_id}", status_code=status.HTTP_204_NO_CONTENT, dependencies=[Depends(require_permission("backups.manage"))])
def delete_backup_job(
    job_id: uuid.UUID, request: Request, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)
) -> None:
    job = db.get(BackupJob, job_id)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job de respaldo no encontrado")
    db.delete(job)
    db.commit()
    log_action(db, current_user, "backup_job.deleted", "backup_job", job_id, request=request)


@router.get("/backup-jobs/{job_id}/runs", response_model=BackupRunPage)
def list_backup_runs(
    job_id: uuid.UUID,
    limit: int = Query(default=10, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
) -> BackupRunPage:
    base_query = select(BackupRun).where(BackupRun.backup_job_id == job_id)
    total = db.scalar(select(func.count()).select_from(base_query.subquery())) or 0
    items = list(db.scalars(base_query.order_by(BackupRun.id.desc()).offset(offset).limit(limit)))
    return BackupRunPage(items=items, total=total)


@router.post(
    "/backup-jobs/{job_id}/run",
    response_model=BackupRunRead,
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(require_permission("backups.manage"))],
)
async def run_backup_job(
    job_id: uuid.UUID, request: Request, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)
) -> BackupRun:
    job = db.get(BackupJob, job_id)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job de respaldo no encontrado")
    service = db.get(Service, job.service_id)
    if service is None or service.server_id is None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="El servicio no tiene servidor asignado")

    run = BackupRun(backup_job_id=job.id, status=RunStatus.pending, triggered_by=TriggerType.manual, started_at=datetime.now(timezone.utc))
    db.add(run)
    db.commit()
    db.refresh(run)
    log_action(
        db, current_user, "backup.triggered", "backup_run", run.id,
        details={"backup_job_id": str(job.id), "type": job.type.value}, request=request,
    )

    if not hub.is_connected(service.server_id):
        run.status = RunStatus.failed
        run.error_message = "El Agente CITI de este servidor no está conectado."
        run.finished_at = datetime.now(timezone.utc)
        db.commit()
    else:
        if job.type == BackupType.database:
            creds = _get_db_credentials(db, job.service_id)
            command = {
                "type": "backup_database",
                "backup_run_id": str(run.id),
                "host": creds["DB_HOST"],
                "port": creds["DB_PORT"],
                "dbname": creds["DB_NAME"],
                "user": creds["DB_USER"],
                "password": creds["DB_PASSWORD"],
                "storage_path": job.storage_path,
            }
        else:
            command = {
                "type": "backup",
                "backup_run_id": str(run.id),
                "source_path": job.source_path,
                "storage_path": job.storage_path,
            }

        future = hub.create_pending_result(run.id)
        dispatched = await hub.send_command(service.server_id, command)
        if not dispatched:
            hub.discard_pending_result(run.id)
            run.status = RunStatus.failed
            run.error_message = "No se pudo enviar el comando al Agente CITI."
            run.finished_at = datetime.now(timezone.utc)
            db.commit()
        else:
            try:
                await asyncio.wait_for(future, timeout=BACKUP_TIMEOUT_SECONDS)
                db.refresh(run)
            except asyncio.TimeoutError:
                hub.discard_pending_result(run.id)
                run.status = RunStatus.failed
                run.error_message = "Tiempo de espera agotado esperando respuesta del Agente CITI."
                run.finished_at = datetime.now(timezone.utc)
                db.commit()

    db.refresh(run)
    if run.status == RunStatus.failed:
        await notify_incident(
            db,
            site_id=site_id_for_server(db, service.server_id),
            severity="critical",
            title=f"Falló el respaldo de {service.name}",
            message=f"El respaldo del servicio '{service.name}' falló: {run.error_message or 'sin detalle'}",
            entity_type="backup_run",
            entity_id=run.id,
            server_id=service.server_id,
        )
    return run


@router.post(
    "/backup-runs/{run_id}/restore",
    response_model=RestoreOperationRead,
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(require_permission("backups.manage"))],
)
async def restore_backup_run(
    run_id: uuid.UUID, request: Request, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)
) -> RestoreOperation:
    run = db.get(BackupRun, run_id)
    if run is None or run.status != RunStatus.success or not run.storage_path:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="El respaldo no está disponible para restaurar")
    job = db.get(BackupJob, run.backup_job_id)
    service = db.get(Service, job.service_id)
    if service is None or service.server_id is None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="El servicio no tiene servidor asignado")

    restore = RestoreOperation(
        backup_run_id=run.id,
        requested_by_id=current_user.id,
        target_service_id=service.id,
        status=RunStatus.pending,
        started_at=datetime.now(timezone.utc),
    )
    db.add(restore)
    db.commit()
    db.refresh(restore)
    log_action(
        db, current_user, "restore.triggered", "restore_operation", restore.id,
        details={"backup_run_id": str(run.id), "target_service_id": str(service.id)}, request=request,
    )

    if not hub.is_connected(service.server_id):
        restore.status = RunStatus.failed
        restore.notes = "El Agente CITI de este servidor no está conectado."
        restore.finished_at = datetime.now(timezone.utc)
        db.commit()
    else:
        if job.type == BackupType.database:
            creds = _get_db_credentials(db, job.service_id)
            command = {
                "type": "restore_database",
                "restore_id": str(restore.id),
                "host": creds["DB_HOST"],
                "port": creds["DB_PORT"],
                "admin_user": creds["DB_USER"],
                "admin_password": creds["DB_PASSWORD"],
                "source_dbname": creds["DB_NAME"],
                "dump_path": run.storage_path,
            }
        else:
            command = {
                "type": "restore",
                "restore_id": str(restore.id),
                "zip_path": run.storage_path,
                "target_path": job.source_path,
            }

        future = hub.create_pending_result(restore.id)
        dispatched = await hub.send_command(service.server_id, command)
        if not dispatched:
            hub.discard_pending_result(restore.id)
            restore.status = RunStatus.failed
            restore.notes = "No se pudo enviar el comando al Agente CITI."
            restore.finished_at = datetime.now(timezone.utc)
            db.commit()
        else:
            try:
                await asyncio.wait_for(future, timeout=RESTORE_TIMEOUT_SECONDS)
                db.refresh(restore)
            except asyncio.TimeoutError:
                hub.discard_pending_result(restore.id)
                restore.status = RunStatus.failed
                restore.notes = "Tiempo de espera agotado esperando respuesta del Agente CITI."
                restore.finished_at = datetime.now(timezone.utc)
                db.commit()

    db.refresh(restore)
    if restore.status == RunStatus.failed:
        await notify_incident(
            db,
            site_id=site_id_for_server(db, service.server_id),
            severity="critical",
            title=f"Falló la restauración en {service.name}",
            message=f"La restauración sobre el servicio '{service.name}' falló: {restore.notes or 'sin detalle'}",
            entity_type="restore_operation",
            entity_id=restore.id,
            server_id=service.server_id,
        )
    return restore
