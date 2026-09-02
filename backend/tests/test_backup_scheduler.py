"""due_backup_jobs (app/services/backup_scheduler.py) — the cron-due calculation that
drives the scheduler loop in main.py. Doesn't touch execute_backup_run itself (that
dispatches a real command to a connected Agent over the websocket hub — exercised live
against a real test-environment backup job instead, not worth mocking the hub here).

All timestamps here are fixed, not datetime.now() offsets: cron fires align to calendar
boundaries (e.g. "* * * * *" fires at :00 of each minute), not N seconds after an
arbitrary reference point, so a "30s ago" offset can land on either side of a minute
boundary depending on the wall-clock second the test happens to run at. Fixed timestamps
make the due/not-due margin exact and independent of when the suite runs.
"""

from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.models.backups import BackupRun, RunStatus, TriggerType
from app.services.backup_scheduler import due_backup_jobs
from tests.conftest import make_backup_job

REFERENCE = datetime(2026, 1, 1, 12, 0, 30, tzinfo=timezone.utc)


def test_job_with_no_prior_run_is_due_once_its_schedule_has_elapsed(db_session: Session) -> None:
    job = make_backup_job(db_session, schedule_cron="* * * * *", created_at=REFERENCE - timedelta(hours=2))
    db_session.commit()

    due = due_backup_jobs(db_session, REFERENCE)

    assert job.id in {j.id for j in due}


def test_job_not_yet_due_is_excluded(db_session: Session) -> None:
    job = make_backup_job(db_session, schedule_cron="0 0 1 1 *", created_at=REFERENCE)  # once a year, Jan 1st
    db_session.commit()

    due = due_backup_jobs(db_session, REFERENCE + timedelta(seconds=10))

    assert job.id not in {j.id for j in due}


def test_disabled_job_is_excluded_even_if_schedule_elapsed(db_session: Session) -> None:
    job = make_backup_job(
        db_session, schedule_cron="* * * * *", created_at=REFERENCE - timedelta(hours=2), enabled=False
    )
    db_session.commit()

    due = due_backup_jobs(db_session, REFERENCE)

    assert job.id not in {j.id for j in due}


def test_job_with_no_schedule_is_excluded(db_session: Session) -> None:
    job = make_backup_job(db_session, schedule_cron=None, created_at=REFERENCE - timedelta(hours=2))
    db_session.commit()

    due = due_backup_jobs(db_session, REFERENCE)

    assert job.id not in {j.id for j in due}


def test_due_calculation_is_based_on_last_run_not_job_creation(db_session: Session) -> None:
    """A job created long ago but that ran recently (every-minute schedule) shouldn't be
    due again immediately — due_backup_jobs must look at the last BackupRun, not
    job.created_at, once one exists."""
    job = make_backup_job(db_session, schedule_cron="* * * * *", created_at=REFERENCE - timedelta(days=30))
    db_session.add(
        BackupRun(
            backup_job_id=job.id,
            status=RunStatus.success,
            triggered_by=TriggerType.scheduled,
            started_at=REFERENCE,
        )
    )
    db_session.commit()

    due = due_backup_jobs(db_session, REFERENCE + timedelta(seconds=10))  # well before the next :00 boundary

    assert job.id not in {j.id for j in due}
