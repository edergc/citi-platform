import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_visible_site_ids, require_permission
from app.api.v1.servers import _ensure_visible
from app.core.database import get_db
from app.models.identity import User
from app.models.infrastructure import Server, Site
from app.models.monitoring import AlertEvent, AlertEventStatus, AlertRule, AlertSeverity
from app.schemas.alert_rule import AlertEventRead, AlertRuleCreate, AlertRuleRead, AlertRuleUpdate
from app.services.audit import diff_changed_fields, log_action
from app.services.maintenance_windows import bulk_maintenance_windows, was_under_maintenance

router = APIRouter(prefix="/alert-rules", tags=["alert-rules"], dependencies=[Depends(get_current_user)])


def _to_alert_event_read(
    event: AlertEvent,
    rule: AlertRule,
    hostname: str | None,
    site_id: uuid.UUID | None,
    site_name: str | None,
    ack_name: str | None,
    during_maintenance: bool = False,
) -> AlertEventRead:
    return AlertEventRead(
        id=event.id,
        alert_rule_id=event.alert_rule_id,
        rule_name=rule.name,
        severity=rule.severity,
        metric=rule.metric,
        metric_target=rule.metric_target,
        server_id=event.server_id,
        hostname=hostname,
        site_id=site_id,
        site_name=site_name,
        triggered_at=event.triggered_at,
        resolved_at=event.resolved_at,
        value=event.value,
        status=event.status,
        acknowledged_at=event.acknowledged_at,
        acknowledged_by_id=event.acknowledged_by_id,
        acknowledged_by_name=ack_name,
        during_maintenance=during_maintenance,
    )


@router.get("", response_model=list[AlertRuleRead])
def list_alert_rules(db: Session = Depends(get_db)) -> list[AlertRule]:
    return list(db.scalars(select(AlertRule).order_by(AlertRule.name)))


@router.get("/events", response_model=list[AlertEventRead])
def list_alert_events(
    limit: int = 20,
    status_filter: AlertEventStatus | None = None,
    severity_filter: AlertSeverity | None = None,
    site_id_filter: uuid.UUID | None = None,
    search: str | None = None,
    db: Session = Depends(get_db),
    site_ids: list[uuid.UUID] | None = Depends(get_visible_site_ids),
) -> list[AlertEventRead]:
    limit = max(1, min(limit, 300))
    query = (
        select(AlertEvent, AlertRule, Server.hostname, Server.site_id, Site.name, User.full_name)
        .join(AlertRule, AlertRule.id == AlertEvent.alert_rule_id)
        .outerjoin(Server, Server.id == AlertEvent.server_id)
        .outerjoin(Site, Site.id == Server.site_id)
        .outerjoin(User, User.id == AlertEvent.acknowledged_by_id)
        .order_by(AlertEvent.triggered_at.desc())
        .limit(limit)
    )
    if status_filter is not None:
        query = query.where(AlertEvent.status == status_filter)
    if severity_filter is not None:
        query = query.where(AlertRule.severity == severity_filter)
    if site_id_filter is not None:
        query = query.where(Server.site_id == site_id_filter)
    if search:
        term = f"%{search.strip()}%"
        query = query.where((AlertRule.name.ilike(term)) | (Server.hostname.ilike(term)))
    if site_ids is not None:
        # Global-scope events (server_id is NULL) aren't tied to any one site — only a
        # superuser (site_ids is None) can see those; a site-scoped user only sees events
        # for servers within their own sedes.
        query = query.where(AlertEvent.server_id.isnot(None), Server.site_id.in_(site_ids))

    rows = list(db.execute(query))
    server_ids = {event.server_id for event, *_ in rows if event.server_id is not None}
    site_ids_seen = {site_id for _, _, _, site_id, _, _ in rows if site_id is not None}
    windows_by_server, windows_by_site = bulk_maintenance_windows(db, server_ids=server_ids, site_ids=site_ids_seen)

    return [
        _to_alert_event_read(
            event, rule, hostname, site_id, site_name, ack_name,
            during_maintenance=was_under_maintenance(
                windows_by_server, windows_by_site, server_id=event.server_id, site_id=site_id, at=event.triggered_at
            ),
        )
        for event, rule, hostname, site_id, site_name, ack_name in rows
    ]


@router.post("/events/{event_id}/acknowledge", response_model=AlertEventRead)
def acknowledge_alert_event(
    event_id: uuid.UUID,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    site_ids: list[uuid.UUID] | None = Depends(get_visible_site_ids),
) -> AlertEventRead:
    """Anyone who can see the underlying server may acknowledge its alert — no separate
    permission, matching how server_notes works. Events with no server (global-scope
    rules) are superuser-only, since a site-scoped user has no server to check visibility
    against."""
    event = db.get(AlertEvent, event_id)
    if event is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Evento de alerta no encontrado")

    server: Server | None = None
    if event.server_id is not None:
        server = db.get(Server, event.server_id)
        if server is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Evento de alerta no encontrado")
        _ensure_visible(server, site_ids)
    elif site_ids is not None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Evento de alerta no encontrado")

    event.acknowledged_at = datetime.now(timezone.utc)
    event.acknowledged_by_id = current_user.id
    db.commit()
    db.refresh(event)

    rule = db.get(AlertRule, event.alert_rule_id)
    log_action(
        db, current_user, "alert_event.acknowledged", "alert_event", event.id,
        details={
            "regla": rule.name if rule else None,
            "servidor": server.hostname if server else None,
            "severidad": rule.severity.value if rule else None,
            "valor": event.value,
        },
        request=request,
    )

    site_name = db.scalar(select(Site.name).where(Site.id == server.site_id)) if server and server.site_id else None
    windows_by_server, windows_by_site = bulk_maintenance_windows(
        db,
        server_ids={event.server_id} if event.server_id else set(),
        site_ids={server.site_id} if server and server.site_id else set(),
    )
    return _to_alert_event_read(
        event, rule, server.hostname if server else None, server.site_id if server else None, site_name, current_user.full_name,
        during_maintenance=was_under_maintenance(
            windows_by_server, windows_by_site,
            server_id=event.server_id, site_id=server.site_id if server else None, at=event.triggered_at,
        ),
    )


@router.post(
    "", response_model=AlertRuleRead, status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission("alerts.manage"))],
)
def create_alert_rule(
    payload: AlertRuleCreate, request: Request, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)
) -> AlertRule:
    rule = AlertRule(**payload.model_dump())
    db.add(rule)
    db.commit()
    db.refresh(rule)
    log_action(db, current_user, "alert_rule.created", "alert_rule", rule.id, details={"name": rule.name}, request=request)
    return rule


@router.patch(
    "/{rule_id}", response_model=AlertRuleRead, dependencies=[Depends(require_permission("alerts.manage"))]
)
def update_alert_rule(
    rule_id: uuid.UUID,
    payload: AlertRuleUpdate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> AlertRule:
    rule = db.get(AlertRule, rule_id)
    if rule is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Regla de alerta no encontrada")
    data = payload.model_dump(exclude_unset=True)
    changes = diff_changed_fields(rule, data)
    for field, value in data.items():
        setattr(rule, field, value)
    db.commit()
    db.refresh(rule)
    log_action(
        db, current_user, "alert_rule.updated", "alert_rule", rule.id,
        details={"changes": changes} if changes else None, request=request,
    )
    return rule


@router.delete(
    "/{rule_id}", status_code=status.HTTP_204_NO_CONTENT, dependencies=[Depends(require_permission("alerts.manage"))]
)
def delete_alert_rule(
    rule_id: uuid.UUID, request: Request, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)
) -> None:
    rule = db.get(AlertRule, rule_id)
    if rule is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Regla de alerta no encontrada")
    deleted_name = rule.name
    db.delete(rule)
    db.commit()
    log_action(db, current_user, "alert_rule.deleted", "alert_rule", rule_id, details={"name": deleted_name}, request=request)
