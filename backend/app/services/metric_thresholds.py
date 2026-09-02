"""Threshold-based proactive alerting on agent-reported metrics (RAM/CPU/disk/network
path), driven by admin-configurable AlertRule rows (see app.api.v1.alert_rules)
instead of hardcoded constants. In-memory cooldown, single-process design — same
rationale as app/core/rate_limit.py: CITI's backend runs as a single uvicorn worker,
so a dict guarded by a lock is sufficient without a Redis dependency.
"""

import operator
import time
import uuid
from datetime import datetime, timezone
from threading import Lock

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.models.monitoring import AlertEvent, AlertEventStatus, AlertRule, AlertScope

_CONDITIONS = {
    "gt": operator.gt,
    "lt": operator.lt,
    "gte": operator.ge,
    "lte": operator.le,
    "eq": operator.eq,
}

# metrics.get("network_path") only arrives on the ~1-in-4 heartbeats where the agent's
# own traceroute cycle (every 60s, heartbeats every 15s) just completed — see
# evaluate_metric_alerts, which skips these rules entirely on the other heartbeats
# instead of treating "no fresh sample yet" as "not breaching".
NETWORK_METRICS = {"network_reachable", "network_latency_ms", "network_loss_percent"}

DEFAULT_TEMPLATES = {
    "ram_percent": "Uso de RAM en '{hostname}' alcanzó {value:.1f}% (umbral {threshold:.0f}%).",
    "cpu_percent": "Uso de CPU en '{hostname}' alcanzó {value:.1f}% (umbral {threshold:.0f}%).",
    "disk_percent_used": "El disco {mount} de '{hostname}' alcanzó {value:.1f}% de uso (umbral {threshold:.0f}%).",
    "network_reachable": "El servidor '{hostname}' no está llegando a Core por la ruta de red (última muestra sin respuesta).",
    "network_latency_ms": "La latencia de red hacia Core en '{hostname}' alcanzó {value:.0f} ms (umbral {threshold:.0f} ms).",
    "network_loss_percent": "La pérdida de paquetes hacia Core en '{hostname}' alcanzó {value:.0f}% (umbral {threshold:.0f}%).",
}


class _Cooldown:
    def __init__(self) -> None:
        self._last_sent: dict[str, float] = {}
        self._lock = Lock()

    def ready(self, key: str, cooldown_seconds: float) -> bool:
        now = time.monotonic()
        with self._lock:
            last = self._last_sent.get(key)
            if last is not None and now - last < cooldown_seconds:
                return False
            self._last_sent[key] = now
            return True


_cooldown = _Cooldown()


def resolve_metric_value(rule: AlertRule, metrics: dict) -> tuple[float | None, str | None]:
    """Returns (value, mount) for the metric this rule watches. `mount` is only
    meaningful for disk_percent_used — the specific disk the value came from."""
    if rule.metric in ("ram_percent", "cpu_percent"):
        return metrics.get(rule.metric), None

    if rule.metric == "disk_percent_used":
        disks = metrics.get("disks") or []
        if rule.metric_target:
            for disk in disks:
                if disk.get("mount") == rule.metric_target:
                    return disk.get("percent_used"), disk.get("mount")
            return None, rule.metric_target
        # No specific disk configured: track the single worst disk (same semantics as
        # ServerMetricHistory.disk_percent_used) so there's exactly one open/resolved
        # AlertEvent lineage per (rule, server) instead of one per disk.
        worst = max(disks, key=lambda d: d.get("percent_used", 0), default=None)
        if worst is None:
            return None, None
        return worst.get("percent_used"), worst.get("mount")

    if rule.metric in NETWORK_METRICS:
        network_path = metrics.get("network_path")
        hops = (network_path or {}).get("hops") or []

        if rule.metric == "network_reachable":
            if network_path is None:
                return None, None
            # Encoded as 1.0/0.0 to reuse the generic condition/threshold mechanism
            # (this rule is always created as condition="eq", threshold=0 — see
            # AlertRuleFormDialog) instead of a bespoke boolean rule type.
            return (1.0 if network_path.get("reachable") else 0.0), None

        if not hops:
            return None, None
        final_hop = hops[-1]  # the destination itself, not an intermediate router
        if rule.metric == "network_latency_ms":
            return final_hop.get("avg_latency_ms"), None
        return final_hop.get("packet_loss_percent"), None

    return None, None


def is_breaching(rule: AlertRule, metrics: dict) -> tuple[bool, float | None, str | None]:
    """Pure check (no side effects, no cooldown) — used both by evaluate_metric_alerts and
    by read-only callers like the servers fleet summary that need "is this breaching right
    now" without triggering a notification or touching AlertEvent state."""
    value, mount = resolve_metric_value(rule, metrics)
    if value is None:
        return False, None, mount
    return _CONDITIONS[rule.condition.value](value, rule.threshold), value, mount


def load_applicable_rules(db: Session, server_id: uuid.UUID) -> list[AlertRule]:
    return list(
        db.scalars(
            select(AlertRule).where(
                AlertRule.enabled.is_(True),
                AlertRule.scope_type == AlertScope.server,
                or_(AlertRule.scope_id.is_(None), AlertRule.scope_id == server_id),
            )
        )
    )


def evaluate_metric_alerts(db: Session, server_id: uuid.UUID, hostname: str, metrics: dict) -> list[dict]:
    """Loads enabled AlertRule rows applicable to this server (global — scope_id is NULL —
    or scoped specifically to it), evaluates each against the latest heartbeat metrics, and
    returns {severity, title, message} dicts ready for notify_incident(). Also persists
    AlertEvent rows: opens one on a fresh cooldown-gated breach, and auto-resolves an open
    one — independent of cooldown, so resolution isn't stuck waiting on the same clock as
    re-notification — once the condition clears."""
    rules = load_applicable_rules(db, server_id)
    alerts: list[dict] = []

    for rule in rules:
        if rule.metric in NETWORK_METRICS and metrics.get("network_path") is None:
            # No fresh traceroute sample on this heartbeat (only ~1 in 4 carries one) —
            # skip entirely rather than let is_breaching's "value is None → not
            # breaching" fallback auto-resolve an open alert every cycle in between.
            continue

        breaching, value, mount = is_breaching(rule, metrics)

        open_event = db.scalar(
            select(AlertEvent).where(
                AlertEvent.alert_rule_id == rule.id,
                AlertEvent.server_id == server_id,
                AlertEvent.status == AlertEventStatus.open,
            )
        )

        if not breaching:
            if open_event is not None:
                open_event.resolved_at = datetime.now(timezone.utc)
                open_event.status = AlertEventStatus.resolved
                db.commit()
            continue

        if not _cooldown.ready(f"{rule.id}:{server_id}", rule.cooldown_minutes * 60):
            continue

        default_template = DEFAULT_TEMPLATES.get(rule.metric, "{hostname}: alerta de '{rule_name}'.")
        template = rule.custom_message or default_template
        format_kwargs = {"hostname": hostname, "value": value, "mount": mount or "", "threshold": rule.threshold}
        try:
            message = template.format(**format_kwargs)
        except (KeyError, IndexError, ValueError):
            # Admin-typed custom_message can reference a placeholder that doesn't exist
            # (e.g. a typo) — never let that crash the heartbeat handler.
            message = default_template.format(**format_kwargs, rule_name=rule.name)

        if open_event is None:
            db.add(
                AlertEvent(
                    alert_rule_id=rule.id,
                    server_id=server_id,
                    triggered_at=datetime.now(timezone.utc),
                    value=value,
                    status=AlertEventStatus.open,
                )
            )
            db.commit()

        alerts.append({"severity": rule.severity.value, "title": f"{rule.name}: {hostname}", "message": message})

    return alerts
