import asyncio
import uuid
from datetime import datetime, timezone

from fastapi import HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.agent_hub import hub
from app.core.security import decrypt_secret
from app.models.backups import BackupJob, BackupRun, BackupType, RunStatus, TriggerType
from app.models.config import ConfigEntry
from app.models.identity import User
from app.models.systems import Service
from app.services.audit import log_action
from app.services.incident_notifier import notify_incident, site_id_for_server

BACKUP_TIMEOUT_SECONDS = 120

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


async def execute_backup_run(
    db: Session,
    job: BackupJob,
    triggered_by: TriggerType,
    current_user: User | None = None,
    request: Request | None = None,
) -> BackupRun:
    """Runs one backup for `job` — dispatches the command to the owning server's Agent
    and waits for the result. Shared by the manual 'Ejecutar ahora' endpoint
    (triggered_by=manual, has a real current_user/request) and the scheduler loop in
    main.py (triggered_by=scheduled, no user/request — see log_action's None handling)."""
    service = db.get(Service, job.service_id)
    if service is None or service.server_id is None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="El servicio no tiene servidor asignado")

    run = BackupRun(backup_job_id=job.id, status=RunStatus.pending, triggered_by=triggered_by, started_at=datetime.now(timezone.utc))
    db.add(run)
    db.commit()
    db.refresh(run)
    log_action(
        db, current_user, "backup.triggered", "backup_run", run.id,
        details={"backup_job_id": str(job.id), "type": job.type.value, "triggered_by": triggered_by.value}, request=request,
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


def due_backup_jobs(db: Session, now: datetime) -> list[BackupJob]:
    """Enabled jobs with a valid schedule_cron whose next scheduled fire time (computed
    from the job's last run, or its creation time if it has never run) is at or before
    `now`. Caller is expected to call this roughly every SCHEDULER_POLL_INTERVAL — a job
    is considered due at most once per poll, since the next croniter step is always
    computed from the last actual run, not from a fixed calendar grid."""
    from croniter import CroniterBadCronError, croniter

    jobs = list(db.scalars(select(BackupJob).where(BackupJob.enabled.is_(True), BackupJob.schedule_cron.is_not(None))))
    due: list[BackupJob] = []
    for job in jobs:
        if not job.schedule_cron:
            continue
        last_run = db.scalar(
            select(BackupRun).where(BackupRun.backup_job_id == job.id).order_by(BackupRun.started_at.desc()).limit(1)
        )
        base = last_run.started_at if last_run and last_run.started_at else job.created_at
        try:
            next_fire = croniter(job.schedule_cron, base).get_next(datetime)
        except (CroniterBadCronError, ValueError):
            continue
        if next_fire.tzinfo is None:
            next_fire = next_fire.replace(tzinfo=timezone.utc)
        if next_fire <= now:
            due.append(job)
    return due
