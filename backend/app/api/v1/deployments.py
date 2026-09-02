import asyncio
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_permission
from app.api.v1.platform_secrets import get_platform_secret
from app.core.agent_hub import hub
from app.core.database import get_db
from app.models.identity import User
from app.models.systems import ActionResultStatus, Service, ServiceAction, ServiceActionLog, ServiceStatus, ServiceType, System
from app.models.versions import Deployment, DeploymentSource, DeploymentStatus, SystemVersion, VersionStatus
from app.schemas.deployment import DeployCheckResponse, DeploymentRead
from app.services.audit import log_action
from app.services.incident_notifier import notify_incident, site_id_for_server

router = APIRouter(tags=["deployments"], dependencies=[Depends(get_current_user)])


async def _notify_deploy_failure(db: Session, system: System, server_id: uuid.UUID, deployment: Deployment, action_label: str) -> None:
    await notify_incident(
        db,
        site_id=site_id_for_server(db, server_id),
        severity="critical",
        title=f"Falló el {action_label} de {system.name}",
        message=f"El {action_label} del sistema '{system.name}' falló: {deployment.log_output or 'sin detalle'}",
        entity_type="deployment",
        entity_id=deployment.id,
        server_id=server_id,
    )

GIT_TIMEOUT_SECONDS = 60
DEPLOY_TIMEOUT_SECONDS = 300
RESTART_TIMEOUT_SECONDS = 30


def _get_system_and_server(db: Session, system_id: uuid.UUID) -> tuple[System, uuid.UUID]:
    system = db.get(System, system_id)
    if system is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sistema no encontrado")
    if not system.repo_url or not system.repo_local_path:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="El sistema no tiene repo_url y/o repo_local_path configurados.",
        )
    service_with_server = db.scalar(
        select(Service).where(Service.system_id == system_id, Service.server_id.isnot(None))
    )
    if service_with_server is None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Ningún servicio de este sistema tiene servidor asignado")
    return system, service_with_server.server_id


def _require_github_token(db: Session) -> str:
    token = get_platform_secret(db, "GITHUB_PAT")
    if not token:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="No hay un GitHub Personal Access Token configurado (PUT /api/v1/platform-secrets/GITHUB_PAT)",
        )
    return token


@router.post("/systems/{system_id}/deploy/check", response_model=DeployCheckResponse, dependencies=[Depends(require_permission("deployments.manage"))])
async def check_deploy_status(system_id: uuid.UUID, db: Session = Depends(get_db)) -> DeployCheckResponse:
    system, server_id = _get_system_and_server(db, system_id)
    token = _require_github_token(db)

    if not hub.is_connected(server_id):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="El Agente CITI de este servidor no está conectado.")

    request_id = uuid.uuid4()
    future = hub.create_pending_result(request_id)
    await hub.send_command(
        server_id,
        {
            "type": "git_status",
            "request_id": str(request_id),
            "repo_path": system.repo_local_path,
            "repo_url": system.repo_url,
            "branch": system.default_branch or "main",
            "token": token,
        },
    )
    try:
        result = await asyncio.wait_for(future, timeout=GIT_TIMEOUT_SECONDS)
    except asyncio.TimeoutError:
        hub.discard_pending_result(request_id)
        raise HTTPException(status_code=status.HTTP_504_GATEWAY_TIMEOUT, detail="Tiempo de espera agotado consultando el estado de Git")

    return DeployCheckResponse(
        is_dirty=result.get("is_dirty", False),
        dirty_files=result.get("dirty_files", []),
        current_commit=result.get("current_commit"),
        remote_commit=result.get("remote_commit"),
        commits_behind=result.get("commits_behind", 0),
        error=result.get("error"),
    )


async def _restart_system_services(db: Session, system_id: uuid.UUID, user_id: uuid.UUID) -> list[str]:
    services = db.scalars(
        select(Service).where(Service.system_id == system_id, Service.type != ServiceType.database, Service.server_id.isnot(None))
    )
    log_lines: list[str] = []
    for service in services:
        action_log = ServiceActionLog(
            service_id=service.id,
            action=ServiceAction.restart,
            triggered_by_id=user_id,
            status=ActionResultStatus.pending,
            started_at=datetime.now(timezone.utc),
        )
        db.add(action_log)
        db.commit()
        db.refresh(action_log)

        if not hub.is_connected(service.server_id):
            log_lines.append(f"{service.name}: agente no conectado, no se reinició")
            continue

        future = hub.create_pending_result(action_log.id)
        await hub.send_command(
            service.server_id,
            {
                "type": "command",
                "action_log_id": str(action_log.id),
                "service_id": str(service.id),
                "control_identifier": service.control_identifier,
                "action": "restart",
            },
        )
        try:
            await asyncio.wait_for(future, timeout=RESTART_TIMEOUT_SECONDS)
            db.refresh(action_log)
        except asyncio.TimeoutError:
            hub.discard_pending_result(action_log.id)
            log_lines.append(f"{service.name}: tiempo de espera agotado al reiniciar")
            continue

        if action_log.status == ActionResultStatus.success:
            service.status = ServiceStatus.running
            log_lines.append(f"{service.name}: reiniciado correctamente")
        else:
            service.status = ServiceStatus.degraded
            log_lines.append(f"{service.name}: falló el reinicio — {action_log.output}")
        service.last_checked_at = datetime.now(timezone.utc)
        db.commit()

    return log_lines


@router.post(
    "/systems/{system_id}/deploy",
    response_model=DeploymentRead,
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(require_permission("deployments.manage"))],
)
async def deploy_system(
    system_id: uuid.UUID, request: Request, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)
) -> Deployment:
    system, server_id = _get_system_and_server(db, system_id)
    token = _require_github_token(db)

    deployment = Deployment(
        system_id=system_id,
        source=DeploymentSource.git,
        status=DeploymentStatus.running,
        triggered_by_id=current_user.id,
        started_at=datetime.now(timezone.utc),
    )
    db.add(deployment)
    db.commit()
    db.refresh(deployment)
    log_action(
        db, current_user, "deployment.triggered", "deployment", deployment.id,
        details={"system_id": str(system_id)}, request=request,
    )

    if not hub.is_connected(server_id):
        deployment.status = DeploymentStatus.failed
        deployment.log_output = "El Agente CITI de este servidor no está conectado."
        deployment.finished_at = datetime.now(timezone.utc)
        db.commit()
        await _notify_deploy_failure(db, system, server_id, deployment, "despliegue")
        return deployment

    deploy_id = uuid.uuid4()
    future = hub.create_pending_result(deploy_id)
    await hub.send_command(
        server_id,
        {
            "type": "deploy",
            "deployment_id": str(deploy_id),
            "repo_path": system.repo_local_path,
            "repo_url": system.repo_url,
            "branch": system.default_branch or "main",
            "target_commit": None,
            "build_command": system.deploy_build_command,
            "token": token,
        },
    )
    try:
        result = await asyncio.wait_for(future, timeout=DEPLOY_TIMEOUT_SECONDS)
    except asyncio.TimeoutError:
        hub.discard_pending_result(deploy_id)
        deployment.status = DeploymentStatus.failed
        deployment.log_output = "Tiempo de espera agotado ejecutando el despliegue."
        deployment.finished_at = datetime.now(timezone.utc)
        db.commit()
        await _notify_deploy_failure(db, system, server_id, deployment, "despliegue")
        return deployment

    if result.get("status") != "success":
        deployment.status = DeploymentStatus.failed
        deployment.log_output = result.get("error") or result.get("output") or "Error desconocido"
        deployment.finished_at = datetime.now(timezone.utc)
        db.commit()
        await _notify_deploy_failure(db, system, server_id, deployment, "despliegue")
        return deployment

    new_commit = result.get("new_commit")
    version = SystemVersion(
        system_id=system_id,
        version_number=(new_commit or "unknown")[:12],
        git_commit_hash=new_commit,
        git_branch=system.default_branch,
        release_notes="Desplegado automáticamente desde CITI",
        status=VersionStatus.active,
        released_by_id=current_user.id,
        released_at=datetime.now(timezone.utc),
    )
    previously_active = db.scalars(
        select(SystemVersion).where(SystemVersion.system_id == system_id, SystemVersion.status == VersionStatus.active)
    )
    for v in previously_active:
        v.status = VersionStatus.deprecated
    db.add(version)
    db.commit()
    db.refresh(version)

    restart_log = await _restart_system_services(db, system_id, current_user.id)

    deployment.version_id = version.id
    deployment.status = DeploymentStatus.success
    deployment.log_output = (result.get("output") or "") + "\n\n" + "\n".join(restart_log)
    deployment.finished_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(deployment)
    return deployment


@router.post(
    "/systems/{system_id}/deploy/rollback/{version_id}",
    response_model=DeploymentRead,
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(require_permission("deployments.manage"))],
)
async def rollback_deployment(
    system_id: uuid.UUID,
    version_id: uuid.UUID,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Deployment:
    system, server_id = _get_system_and_server(db, system_id)
    token = _require_github_token(db)

    target_version = db.get(SystemVersion, version_id)
    if target_version is None or target_version.system_id != system_id or not target_version.git_commit_hash:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Versión no encontrada o sin commit registrado")

    last_deployment = db.scalar(
        select(Deployment).where(Deployment.system_id == system_id).order_by(Deployment.started_at.desc())
    )

    deployment = Deployment(
        system_id=system_id,
        source=DeploymentSource.git,
        status=DeploymentStatus.running,
        triggered_by_id=current_user.id,
        started_at=datetime.now(timezone.utc),
        rollback_of_id=last_deployment.id if last_deployment else None,
    )
    db.add(deployment)
    db.commit()
    db.refresh(deployment)
    log_action(
        db, current_user, "deployment.rollback_triggered", "deployment", deployment.id,
        details={"system_id": str(system_id), "target_version_id": str(version_id)}, request=request,
    )

    if not hub.is_connected(server_id):
        deployment.status = DeploymentStatus.failed
        deployment.log_output = "El Agente CITI de este servidor no está conectado."
        deployment.finished_at = datetime.now(timezone.utc)
        db.commit()
        await _notify_deploy_failure(db, system, server_id, deployment, "rollback")
        return deployment

    deploy_id = uuid.uuid4()
    future = hub.create_pending_result(deploy_id)
    await hub.send_command(
        server_id,
        {
            "type": "deploy",
            "deployment_id": str(deploy_id),
            "repo_path": system.repo_local_path,
            "repo_url": system.repo_url,
            "branch": system.default_branch or "main",
            "target_commit": target_version.git_commit_hash,
            "build_command": system.deploy_build_command,
            "token": token,
        },
    )
    try:
        result = await asyncio.wait_for(future, timeout=DEPLOY_TIMEOUT_SECONDS)
    except asyncio.TimeoutError:
        hub.discard_pending_result(deploy_id)
        deployment.status = DeploymentStatus.failed
        deployment.log_output = "Tiempo de espera agotado ejecutando el rollback."
        deployment.finished_at = datetime.now(timezone.utc)
        db.commit()
        await _notify_deploy_failure(db, system, server_id, deployment, "rollback")
        return deployment

    if result.get("status") != "success":
        deployment.status = DeploymentStatus.failed
        deployment.log_output = result.get("error") or result.get("output") or "Error desconocido"
        deployment.finished_at = datetime.now(timezone.utc)
        db.commit()
        await _notify_deploy_failure(db, system, server_id, deployment, "rollback")
        return deployment

    currently_active = db.scalars(
        select(SystemVersion).where(SystemVersion.system_id == system_id, SystemVersion.status == VersionStatus.active)
    )
    for v in currently_active:
        v.status = VersionStatus.rolled_back
    target_version.status = VersionStatus.active
    db.commit()

    restart_log = await _restart_system_services(db, system_id, current_user.id)

    deployment.version_id = target_version.id
    deployment.status = DeploymentStatus.rolled_back
    deployment.log_output = (result.get("output") or "") + "\n\n" + "\n".join(restart_log)
    deployment.finished_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(deployment)
    return deployment


@router.get("/systems/{system_id}/deployments", response_model=list[DeploymentRead])
def list_deployments(system_id: uuid.UUID, db: Session = Depends(get_db)) -> list[Deployment]:
    query = select(Deployment).where(Deployment.system_id == system_id).order_by(Deployment.started_at.desc())
    return list(db.scalars(query))
