import asyncio
import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.router import api_router
from app.core.config import settings
from app.core.database import SessionLocal
from app.services.agent_watchdog import close_stale_agent_connections
from app.services.backup_retention import purge_expired_backups
from app.services.metrics_retention import purge_old_metric_history, purge_old_network_path_history
from app.services.synthetic_checks import run_all_checks
from app.services.weekly_report import _next_run_at, send_weekly_report

logger = logging.getLogger("citi.scheduler")

BACKUP_RETENTION_INTERVAL_SECONDS = 24 * 60 * 60
METRICS_RETENTION_INTERVAL_SECONDS = 24 * 60 * 60
WEEKLY_REPORT_FAILURE_BACKOFF_SECONDS = 60 * 60
AGENT_WATCHDOG_INTERVAL_SECONDS = 20
SYNTHETIC_CHECK_INTERVAL_SECONDS = 5 * 60


async def _backup_retention_loop() -> None:
    """Runs once at startup, then every 24h for the lifetime of the process."""
    while True:
        try:
            db = SessionLocal()
            try:
                purged = await asyncio.to_thread(purge_expired_backups, db)
                if purged:
                    logger.info("Purga de backups: %d archivo(s) eliminado(s)", len(purged))
            finally:
                db.close()
        except Exception:
            logger.exception("Error ejecutando la purga de backups")
        await asyncio.sleep(BACKUP_RETENTION_INTERVAL_SECONDS)


async def _metrics_retention_loop() -> None:
    """Runs once at startup, then every 24h for the lifetime of the process."""
    while True:
        try:
            db = SessionLocal()
            try:
                deleted = await asyncio.to_thread(purge_old_metric_history, db)
                if deleted:
                    logger.info("Purga de historial de métricas: %d fila(s) eliminada(s)", deleted)
                deleted_paths = await asyncio.to_thread(purge_old_network_path_history, db)
                if deleted_paths:
                    logger.info("Purga de historial de ruta de red: %d fila(s) eliminada(s)", deleted_paths)
            finally:
                db.close()
        except Exception:
            logger.exception("Error ejecutando la purga de historial de métricas")
        await asyncio.sleep(METRICS_RETENTION_INTERVAL_SECONDS)


async def _weekly_report_loop() -> None:
    """Sleeps until the next Monday 08:00 Lima time, sends the report, repeats. A failed
    attempt backs off an hour and retries rather than waiting a full week."""
    while True:
        try:
            now = datetime.now(timezone.utc)
            sleep_seconds = (_next_run_at(now) - now).total_seconds()
            await asyncio.sleep(max(sleep_seconds, 0))
            db = SessionLocal()
            try:
                await send_weekly_report(db)
                logger.info("Reporte semanal enviado")
            finally:
                db.close()
        except Exception:
            logger.exception("Error enviando el reporte semanal")
            await asyncio.sleep(WEEKLY_REPORT_FAILURE_BACKOFF_SECONDS)


async def _agent_watchdog_loop() -> None:
    """Runs every AGENT_WATCHDOG_INTERVAL_SECONDS for the lifetime of the process — see
    app/services/agent_watchdog.py for why this exists."""
    while True:
        await asyncio.sleep(AGENT_WATCHDOG_INTERVAL_SECONDS)
        try:
            db = SessionLocal()
            try:
                closed = await close_stale_agent_connections(db)
                if closed:
                    logger.info("Vigilante de conectividad: %d agente(s) sin heartbeat forzado(s) a desconectar", closed)
            finally:
                db.close()
        except Exception:
            logger.exception("Error ejecutando el vigilante de conectividad de agentes")


async def _synthetic_check_loop() -> None:
    """Runs once at startup, then every SYNTHETIC_CHECK_INTERVAL_SECONDS — see
    app/services/synthetic_checks.py for what a "check" is."""
    while True:
        try:
            db = SessionLocal()
            try:
                results = await run_all_checks(db)
                if results:
                    logger.info("Chequeos sintéticos: %d resultado(s)", len(results))
            finally:
                db.close()
        except Exception:
            logger.exception("Error ejecutando los chequeos sintéticos")
        await asyncio.sleep(SYNTHETIC_CHECK_INTERVAL_SECONDS)


@asynccontextmanager
async def lifespan(app: FastAPI):
    backup_task = asyncio.create_task(_backup_retention_loop())
    metrics_task = asyncio.create_task(_metrics_retention_loop())
    report_task = asyncio.create_task(_weekly_report_loop())
    watchdog_task = asyncio.create_task(_agent_watchdog_loop())
    synthetic_task = asyncio.create_task(_synthetic_check_loop())
    yield
    backup_task.cancel()
    metrics_task.cancel()
    report_task.cancel()
    watchdog_task.cancel()
    synthetic_task.cancel()


app = FastAPI(title=settings.PROJECT_NAME, version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router, prefix=settings.API_V1_PREFIX)


@app.get("/health", tags=["health"])
def health() -> dict[str, str]:
    return {"status": "ok"}
