"""Prunes ServerMetricHistory rows older than the retention window. One row is written
per server roughly every 5 minutes (see agents.py's heartbeat handler), so without this
the table grows forever — nothing currently queries it past 90 days (the metrics/history
trend chart caps at 30 days; the uptime endpoint's 90-day cap is the widest window used
anywhere in the app), so that's the retention window here too.
"""

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.models.infrastructure import ServerMetricHistory, ServerNetworkPathHistory

logger = logging.getLogger("citi.metrics_retention")

RETENTION_DAYS = 90

# Network-path history writes one row per server roughly every 60s (~8x the rate of
# ServerMetricHistory) with a full hop list per row, so it's kept on a shorter window —
# this is recent diagnostic detail for troubleshooting, not a long-term capacity trend
# like disk/CPU/RAM history.
NETWORK_PATH_RETENTION_DAYS = 14


def purge_old_metric_history(db: Session, retention_days: int = RETENTION_DAYS) -> int:
    cutoff = datetime.now(timezone.utc) - timedelta(days=retention_days)
    result = db.execute(delete(ServerMetricHistory).where(ServerMetricHistory.recorded_at < cutoff))
    db.commit()
    return result.rowcount or 0


def purge_old_network_path_history(db: Session, retention_days: int = NETWORK_PATH_RETENTION_DAYS) -> int:
    cutoff = datetime.now(timezone.utc) - timedelta(days=retention_days)
    result = db.execute(delete(ServerNetworkPathHistory).where(ServerNetworkPathHistory.recorded_at < cutoff))
    db.commit()
    return result.rowcount or 0
