import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict

from app.models.monitoring import AlertCondition, AlertEventStatus, AlertScope, AlertSeverity

AlertMetric = Literal[
    "ram_percent", "cpu_percent", "disk_percent_used",
    "network_reachable", "network_latency_ms", "network_loss_percent",
]


class AlertRuleCreate(BaseModel):
    name: str
    scope_type: AlertScope = AlertScope.server
    scope_id: uuid.UUID | None = None
    metric: AlertMetric
    metric_target: str | None = None
    condition: AlertCondition
    threshold: float
    severity: AlertSeverity = AlertSeverity.warning
    custom_message: str | None = None
    cooldown_minutes: int = 30
    enabled: bool = True


class AlertRuleUpdate(BaseModel):
    name: str | None = None
    scope_type: AlertScope | None = None
    scope_id: uuid.UUID | None = None
    metric: AlertMetric | None = None
    metric_target: str | None = None
    condition: AlertCondition | None = None
    threshold: float | None = None
    severity: AlertSeverity | None = None
    custom_message: str | None = None
    cooldown_minutes: int | None = None
    enabled: bool | None = None


class AlertRuleRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    scope_type: AlertScope
    scope_id: uuid.UUID | None
    metric: str
    metric_target: str | None
    condition: AlertCondition
    threshold: float
    severity: AlertSeverity
    custom_message: str | None
    cooldown_minutes: int
    enabled: bool
    created_at: datetime


class AlertEventRead(BaseModel):
    id: uuid.UUID
    alert_rule_id: uuid.UUID
    rule_name: str
    severity: AlertSeverity
    metric: str
    metric_target: str | None
    server_id: uuid.UUID | None
    hostname: str | None
    site_id: uuid.UUID | None
    site_name: str | None
    triggered_at: datetime
    resolved_at: datetime | None
    value: float | None
    status: AlertEventStatus
    acknowledged_at: datetime | None = None
    acknowledged_by_id: uuid.UUID | None = None
    acknowledged_by_name: str | None = None
    during_maintenance: bool = False
