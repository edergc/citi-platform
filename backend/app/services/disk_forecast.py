"""Projects when a server's worst disk will fill up, from its own recent
ServerMetricHistory.disk_percent_used trend — plain linear regression, no new
dependency, consistent with how the disk_percent_used alert rule already treats "the
worst disk" as a single number per heartbeat sample (see metric_thresholds.py).
"""

import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.infrastructure import ServerMetricHistory
from app.schemas.server import DiskForecast

# Below this many samples, a regression is too noisy to trust — report the current
# value only, no trend/projection.
MIN_SAMPLES = 6

# A slope this close to zero (or negative) reads as "not meaningfully growing" rather
# than projecting a wildly distant or negative "days until full".
MIN_SLOPE_PERCENT_PER_DAY = 0.01


def compute_disk_forecast(db: Session, server_id: uuid.UUID, days: int) -> DiskForecast:
    since = datetime.now(timezone.utc) - timedelta(days=days)
    rows = list(
        db.execute(
            select(ServerMetricHistory.recorded_at, ServerMetricHistory.disk_percent_used)
            .where(
                ServerMetricHistory.server_id == server_id,
                ServerMetricHistory.recorded_at >= since,
                ServerMetricHistory.disk_percent_used.isnot(None),
            )
            .order_by(ServerMetricHistory.recorded_at)
        )
    )

    if not rows:
        return DiskForecast(sample_days=days, sample_count=0, current_percent=None, trend_percent_per_day=None, days_until_full=None)

    current_percent = rows[-1][1]
    if len(rows) < MIN_SAMPLES:
        return DiskForecast(
            sample_days=days, sample_count=len(rows), current_percent=current_percent, trend_percent_per_day=None, days_until_full=None
        )

    t0 = rows[0][0]
    xs = [(t - t0).total_seconds() / 86400 for t, _ in rows]  # days since first sample
    ys = [y for _, y in rows]

    n = len(xs)
    x_mean = sum(xs) / n
    y_mean = sum(ys) / n
    denominator = sum((x - x_mean) ** 2 for x in xs)

    if denominator == 0:
        return DiskForecast(
            sample_days=days, sample_count=n, current_percent=current_percent, trend_percent_per_day=None, days_until_full=None
        )

    slope = sum((x - x_mean) * (y - y_mean) for x, y in zip(xs, ys)) / denominator  # % per day

    if slope <= MIN_SLOPE_PERCENT_PER_DAY:
        return DiskForecast(
            sample_days=days, sample_count=n, current_percent=current_percent, trend_percent_per_day=round(slope, 3), days_until_full=None
        )

    days_until_full = max((100 - current_percent) / slope, 0)
    return DiskForecast(
        sample_days=days,
        sample_count=n,
        current_percent=current_percent,
        trend_percent_per_day=round(slope, 3),
        days_until_full=round(days_until_full, 1),
    )
