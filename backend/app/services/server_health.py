"""Composite per-server health signal ("va bien" vs "necesita revisión").

Most técnicos have neither a real email on file nor access to Telegram (institutional
proxy blocks it), so the servers list/detail page is the one channel that reliably reaches
them. This collapses connectivity, open alerts, recent critical Windows events, and
resource thresholds into a single ok/warning/critical badge — plus the short list of
reasons behind it — so a técnico doesn't have to read every metric individually to know
whether a server needs attention right now.
"""

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.infrastructure import Agent, AgentStatus, Server, ServerEvent, ServerStatus
from app.models.monitoring import AlertEvent, AlertEventStatus, AlertRule, AlertScope
from app.schemas.server import ServerHealth
from app.services.metric_thresholds import is_breaching

RECENT_EVENT_WINDOW = timedelta(hours=24)

_METRIC_LABELS = {
    "ram_percent": "RAM",
    "cpu_percent": "CPU",
    "disk_percent_used": "Disco",
}


@dataclass
class ServerHealthResult:
    status: ServerHealth = "ok"
    reasons: list[str] = field(default_factory=list)


def compute_health_map(db: Session, servers: list[Server]) -> dict[uuid.UUID, ServerHealthResult]:
    if not servers:
        return {}
    server_ids = [s.id for s in servers]

    agents_by_server = {a.server_id: a for a in db.scalars(select(Agent).where(Agent.server_id.in_(server_ids)))}

    open_alerts: dict[uuid.UUID, list[tuple[str, bool]]] = {}
    for server_id, severity, acknowledged_at in db.execute(
        select(AlertEvent.server_id, AlertRule.severity, AlertEvent.acknowledged_at)
        .join(AlertRule, AlertRule.id == AlertEvent.alert_rule_id)
        .where(AlertEvent.status == AlertEventStatus.open, AlertEvent.server_id.in_(server_ids))
    ):
        open_alerts.setdefault(server_id, []).append((severity.value, acknowledged_at is not None))

    since = datetime.now(timezone.utc) - RECENT_EVENT_WINDOW
    critical_event_ids: set[uuid.UUID] = set()
    error_event_ids: set[uuid.UUID] = set()
    for server_id, level in db.execute(
        select(ServerEvent.server_id, ServerEvent.level).where(
            ServerEvent.occurred_at >= since, ServerEvent.server_id.in_(server_ids), ServerEvent.level.in_((1, 2))
        )
    ):
        (critical_event_ids if level == 1 else error_event_ids).add(server_id)

    rules = list(
        db.scalars(select(AlertRule).where(AlertRule.enabled.is_(True), AlertRule.scope_type == AlertScope.server))
    )
    global_rules = [r for r in rules if r.scope_id is None]
    rules_by_server: dict[uuid.UUID, list[AlertRule]] = {}
    for rule in rules:
        if rule.scope_id is not None:
            rules_by_server.setdefault(rule.scope_id, []).append(rule)

    results: dict[uuid.UUID, ServerHealthResult] = {}
    for server in servers:
        agent = agents_by_server.get(server.id)

        breaching: dict[str, str] = {}  # metric -> worst severity
        if agent is not None:
            metrics = {"ram_percent": agent.ram_percent, "cpu_percent": agent.cpu_percent, "disks": agent.disks}
            for rule in global_rules + rules_by_server.get(server.id, []):
                hit, _, _ = is_breaching(rule, metrics)
                if not hit:
                    continue
                current = breaching.get(rule.metric)
                if current != "critical":
                    breaching[rule.metric] = rule.severity.value

        alerts = open_alerts.get(server.id, [])
        unacked_critical = sum(1 for sev, acked in alerts if sev == "critical" and not acked)
        other_open = len(alerts) - unacked_critical

        reasons: list[str] = []
        status: ServerHealth = "ok"

        if server.status == ServerStatus.offline:
            status, reasons = "critical", reasons + ["Servidor desconectado"]
        elif agent is not None and agent.status == AgentStatus.unreachable:
            status, reasons = "critical", reasons + ["Agente sin respuesta"]
        elif agent is not None and agent.status == AgentStatus.revoked:
            status, reasons = "critical", reasons + ["Agente revocado"]

        if unacked_critical:
            status = "critical"
            reasons.append(
                f"{unacked_critical} alerta{'s' if unacked_critical != 1 else ''} crítica{'s' if unacked_critical != 1 else ''} sin reconocer"
            )
        if "critical" in breaching.values():
            status = "critical"
            for metric, severity in breaching.items():
                if severity == "critical":
                    reasons.append(f"{_METRIC_LABELS.get(metric, metric)} por encima del umbral crítico")
        if server.id in critical_event_ids:
            status = "critical"
            reasons.append("Evento crítico del sistema en las últimas 24h")

        if status != "critical":
            warning_reasons: list[str] = []
            if server.status == ServerStatus.degraded:
                warning_reasons.append("Servidor en estado degradado")
            if agent is None:
                warning_reasons.append("Agente no instalado")
            elif agent.status == AgentStatus.pending:
                warning_reasons.append("Agente pendiente de conexión")
            if other_open:
                warning_reasons.append(f"{other_open} alerta{'s' if other_open != 1 else ''} abierta{'s' if other_open != 1 else ''}")
            if any(sev == "warning" for metric, sev in breaching.items()):
                for metric, severity in breaching.items():
                    if severity == "warning":
                        warning_reasons.append(f"{_METRIC_LABELS.get(metric, metric)} cerca del umbral")
            if server.id in error_event_ids:
                warning_reasons.append("Error del sistema reciente (últimas 24h)")

            if warning_reasons:
                status = "warning"
                reasons = warning_reasons

        results[server.id] = ServerHealthResult(status=status, reasons=reasons)

    return results


def compute_health(db: Session, server: Server) -> ServerHealthResult:
    return compute_health_map(db, [server])[server.id]
