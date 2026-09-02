"""Enforces BackupJob.retention_days by deleting the on-disk file for backup runs
older than their job's retention window. The BackupRun row itself is kept (with
storage_path cleared and purged_at set) so history/audit trail survives — only the
actual dump/zip file on disk is removed.
"""

import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.backups import BackupJob, BackupRun, RunStatus
from app.services.audit import log_action

logger = logging.getLogger("citi.backup_retention")


def purge_expired_backups(db: Session) -> list[dict]:
    """Runs one purge pass across every enabled BackupJob. Returns a summary per deleted run."""
    purged: list[dict] = []
    now = datetime.now(timezone.utc)

    jobs = list(db.scalars(select(BackupJob)))
    for job in jobs:
        cutoff = now - timedelta(days=job.retention_days)
        expired_runs = db.scalars(
            select(BackupRun).where(
                BackupRun.backup_job_id == job.id,
                BackupRun.status == RunStatus.success,
                BackupRun.storage_path.isnot(None),
                BackupRun.purged_at.is_(None),
                BackupRun.finished_at < cutoff,
            )
        )
        for run in expired_runs:
            path = Path(run.storage_path)
            freed_bytes = run.size_bytes
            try:
                path.unlink(missing_ok=True)
            except OSError as exc:
                logger.warning("No se pudo eliminar el archivo de respaldo %s: %s", path, exc)
                continue

            run.purged_at = now
            run.storage_path = None
            db.commit()

            log_action(
                db,
                None,
                "backup_run.purged",
                "backup_run",
                run.id,
                details={"backup_job_id": str(job.id), "retention_days": job.retention_days, "freed_bytes": freed_bytes},
            )
            purged.append({"run_id": str(run.id), "job_id": str(job.id), "path": str(path)})

    return purged
