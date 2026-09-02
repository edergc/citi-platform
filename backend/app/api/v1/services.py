import asyncio
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_permission
from app.core.agent_hub import hub
from app.core.database import get_db
from app.models.identity import User
from app.models.systems import ActionResultStatus, Service, ServiceAction, ServiceActionLog, ServiceStatus
from app.schemas.service import (
    ServiceActionLogRead,
    ServiceActionRequest,
    ServiceCreate,
    ServiceRead,
    ServiceUpdate,
)
from app.services.audit import diff_changed_fields, log_action
from app.services.incident_notifier import notify_incident, site_id_for_server

AGENT_COMMAND_TIMEOUT_SECONDS = 20

router = APIRouter(prefix="/services", tags=["services"], dependencies=[Depends(get_current_user)])


@router.get("", response_model=list[ServiceRead])
def list_services(
    system_id: uuid.UUID | None = None, server_id: uuid.UUID | None = None, db: Session = Depends(get_db)
) -> list[Service]:
    query = select(Service).order_by(Service.name)
    if system_id is not None:
        query = query.where(Service.system_id == system_id)
    if server_id is not None:
        query = query.where(Service.server_id == server_id)
    return list(db.scalars(query))


@router.post("", response_model=ServiceRead, status_code=status.HTTP_201_CREATED, dependencies=[Depends(require_permission("services.manage"))])
def create_service(
    payload: ServiceCreate, request: Request, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)
) -> Service:
    service = Service(**payload.model_dump())
    db.add(service)
    db.commit()
    db.refresh(service)
    log_action(db, current_user, "service.created", "service", service.id, details={"name": service.name}, request=request)
    return service


@router.get("/{service_id}", response_model=ServiceRead)
def get_service(service_id: uuid.UUID, db: Session = Depends(get_db)) -> Service:
    service = db.get(Service, service_id)
    if service is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Servicio no encontrado")
    return service


@router.patch("/{service_id}", response_model=ServiceRead, dependencies=[Depends(require_permission("services.manage"))])
def update_service(
    service_id: uuid.UUID,
    payload: ServiceUpdate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Service:
    service = db.get(Service, service_id)
    if service is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Servicio no encontrado")
    data = payload.model_dump(exclude_unset=True)
    changes = diff_changed_fields(service, data)
    for field, value in data.items():
        setattr(service, field, value)
    db.commit()
    db.refresh(service)
    log_action(
        db, current_user, "service.updated", "service", service.id,
        details={"changes": changes} if changes else None, request=request,
    )
    return service


@router.delete("/{service_id}", status_code=status.HTTP_204_NO_CONTENT, dependencies=[Depends(require_permission("services.manage"))])
def delete_service(
    service_id: uuid.UUID, request: Request, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)
) -> None:
    service = db.get(Service, service_id)
    if service is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Servicio no encontrado")
    deleted_name = service.name
    db.delete(service)
    db.commit()
    log_action(
        db, current_user, "service.deleted", "service", service_id, details={"name": deleted_name}, request=request
    )


@router.post(
    "/{service_id}/actions",
    response_model=ServiceActionLogRead,
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(require_permission("services.manage"))],
)
async def trigger_service_action(
    service_id: uuid.UUID,
    payload: ServiceActionRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ServiceActionLog:
    """Triggers a start/stop/restart for a service via the CITI Agent connected to its server.

    Blocks until the agent reports a result or AGENT_COMMAND_TIMEOUT_SECONDS elapses.
    """
    service = db.get(Service, service_id)
    if service is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Servicio no encontrado")
    if service.server_id is None or not service.control_identifier:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="El servicio no tiene servidor/identificador de control asignado",
        )

    action_log = ServiceActionLog(
        service_id=service_id,
        action=payload.action,
        triggered_by_id=current_user.id,
        status=ActionResultStatus.pending,
        started_at=datetime.now(timezone.utc),
    )
    db.add(action_log)
    db.commit()
    db.refresh(action_log)
    log_action(
        db, current_user, "service.action_triggered", "service", service.id,
        details={"action": payload.action.value, "service_name": service.name}, request=request,
    )

    if not hub.is_connected(service.server_id):
        action_log.status = ActionResultStatus.failed
        action_log.output = "El Agente CITI de este servidor no está conectado."
        action_log.finished_at = datetime.now(timezone.utc)
    else:
        future = hub.create_pending_result(action_log.id)
        dispatched = await hub.send_command(
            service.server_id,
            {
                "type": "command",
                "action_log_id": str(action_log.id),
                "service_id": str(service.id),
                "control_identifier": service.control_identifier,
                "action": payload.action.value,
            },
        )
        if not dispatched:
            hub.discard_pending_result(action_log.id)
            action_log.status = ActionResultStatus.failed
            action_log.output = "No se pudo enviar el comando al Agente CITI."
            action_log.finished_at = datetime.now(timezone.utc)
        else:
            try:
                await asyncio.wait_for(future, timeout=AGENT_COMMAND_TIMEOUT_SECONDS)
                # The result was written by the agent websocket handler's own DB session
                # (a different Session instance) — this object's attributes are stale until refreshed.
                db.refresh(action_log)
            except asyncio.TimeoutError:
                hub.discard_pending_result(action_log.id)
                action_log.status = ActionResultStatus.failed
                action_log.output = "Tiempo de espera agotado esperando respuesta del Agente CITI."
                action_log.finished_at = datetime.now(timezone.utc)

    if action_log.status == ActionResultStatus.success:
        service.status = ServiceStatus.stopped if payload.action == ServiceAction.stop else ServiceStatus.running
    elif action_log.status == ActionResultStatus.failed:
        service.status = ServiceStatus.degraded
    service.last_checked_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(action_log)

    await _notify_service_action_outcome(db, service, payload.action, action_log)

    return action_log


async def _notify_service_action_outcome(
    db: Session, service: Service, action: ServiceAction, action_log: ServiceActionLog
) -> None:
    site_id = site_id_for_server(db, service.server_id)

    if action_log.status == ActionResultStatus.failed:
        await notify_incident(
            db,
            site_id=site_id,
            severity="critical",
            title=f"Falló {action.value} en {service.name}",
            message=f"La acción '{action.value}' sobre el servicio '{service.name}' falló: {action_log.output or 'sin detalle'}",
            entity_type="service",
            entity_id=service.id,
            server_id=service.server_id,
        )
    elif action == ServiceAction.stop:
        await notify_incident(
            db,
            site_id=site_id,
            severity="warning",
            title=f"Servicio detenido: {service.name}",
            message=f"El servicio '{service.name}' fue detenido correctamente.",
            entity_type="service",
            entity_id=service.id,
            server_id=service.server_id,
        )
    elif action in (ServiceAction.restart, ServiceAction.force_restart):
        await notify_incident(
            db,
            site_id=site_id,
            severity="info",
            title=f"Servicio reiniciado: {service.name}",
            message=f"El servicio '{service.name}' fue reiniciado correctamente.",
            entity_type="service",
            entity_id=service.id,
            server_id=service.server_id,
        )
    # action == start and succeeded: routine, no notification
