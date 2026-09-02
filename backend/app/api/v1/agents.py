import asyncio
import hashlib
import logging
import re
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, Response, WebSocket, WebSocketDisconnect, status
from jose import JWTError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_visible_site_ids, require_superuser
from app.core.agent_hub import hub
from app.core.database import SessionLocal, get_db
from app.core.security import (
    create_agent_token,
    decode_token,
    generate_enrollment_token,
    hash_enrollment_token,
)
from app.models.backups import BackupRun, RestoreOperation, RunStatus
from app.models.identity import User
from app.models.infrastructure import (
    Agent,
    AgentStatus,
    OSType,
    Server,
    ServerEvent,
    ServerMetricHistory,
    ServerNetworkPathHistory,
    ServerStatus,
)
from app.models.systems import ActionResultStatus, Service, ServiceActionLog
from app.schemas.agent import AgentEnrollRequest, AgentEnrollResponse, EnrollTokenResponse
from app.services.agent_installer import AGENT_DIR, build_agent_installer_targz, build_agent_installer_zip
from app.services.audit import log_action
from app.services.incident_notifier import notify_incident
from app.services.metric_thresholds import evaluate_metric_alerts

logger = logging.getLogger("citi.agents_ws")

router = APIRouter(prefix="/agents", tags=["agents"])

# History rows are only worth keeping every few minutes for trend charts — the raw
# heartbeat cadence (~15s) would bloat the table for no benefit.
METRIC_HISTORY_INTERVAL = timedelta(minutes=5)

# Windows event/agent timestamps can carry sub-microsecond precision (e.g.
# "...148635400Z") that datetime.fromisoformat() rejects outright — truncate to
# microseconds before parsing.
_TIMESTAMP_FRAC_RE = re.compile(r"(\.\d{1,6})\d*(Z)?$")


def _parse_agent_timestamp(value: str | None) -> datetime | None:
    if not value:
        return None
    value = _TIMESTAMP_FRAC_RE.sub(r"\1\2", value)
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


_AGENT_VERSION_RE = re.compile(r'^AGENT_VERSION\s*=\s*"([^"]+)"', re.MULTILINE)


def _agent_source_payload() -> dict:
    """Reads agent/citi_agent.py fresh off disk on every call (it's ~35KB, negligible
    cost) rather than caching at import time — so bumping AGENT_VERSION there is the
    entire "release" step for the fleet-wide auto-update below; no backend deploy or
    restart needed to ship a new agent version."""
    source = (AGENT_DIR / "citi_agent.py").read_text(encoding="utf-8")
    match = _AGENT_VERSION_RE.search(source)
    if match is None:
        raise RuntimeError("agent/citi_agent.py no declara AGENT_VERSION")
    return {"version": match.group(1), "sha256": hashlib.sha256(source.encode("utf-8")).hexdigest(), "source": source}


# Best-effort "motivo" for a disconnect, derived from the WebSocket close code Starlette
# hands us in WebSocketDisconnect.code — there's no explicit "goodbye, I'm shutting down
# for reason X" message in the agent protocol, so this is inferred from how the TCP/WS
# layer itself observed the connection end, not a true diagnostic from the remote host.
# 1000/1001 mean *some* endpoint performed a clean WebSocket close handshake (either side
# could have initiated it — the agent process exiting normally, or a network device
# resetting the connection cleanly). 1006 (or no code at all, which uvicorn's ASGI
# implementation reports when the TCP connection simply vanishes with no closing frame)
# is the common signature of a power loss, network cut, or hard crash.
_HEARTBEAT_TIMEOUT_CLOSE_CODE = 4408  # 4000-4999 is reserved for private/app-specific use per RFC 6455

_CLOSE_CODE_REASONS: dict[int, str] = {
    1000: "cierre normal — el agente se detuvo o se reinició de forma controlada",
    1001: "el host se está apagando o el servicio del agente se está deteniendo",
    1006: "conexión perdida sin cierre limpio — probable corte de red, apagado abrupto o pérdida de energía",
    1011: "error interno del servidor durante la conexión",
    _HEARTBEAT_TIMEOUT_CLOSE_CODE: (
        "sin heartbeat recibido a tiempo — el vigilante de conectividad detectó la conexión colgada "
        "(probable corte de red, apagado abrupto o pérdida de energía) sin esperar a que el sistema "
        "operativo notara el socket muerto"
    ),
}


def _disconnect_reason(code: int | None) -> str:
    if code is None:
        return _CLOSE_CODE_REASONS[1006]
    return _CLOSE_CODE_REASONS.get(code, f"conexión cerrada con código {code}")


def _ensure_visible(server: Server, site_ids: list[uuid.UUID] | None) -> None:
    if site_ids is not None and (server.site_id is None or server.site_id not in site_ids):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Servidor no encontrado")


def _issue_enrollment_token(db: Session, server_id: uuid.UUID) -> str:
    plaintext_token = generate_enrollment_token()
    agent = db.scalar(select(Agent).where(Agent.server_id == server_id))
    if agent is None:
        agent = Agent(server_id=server_id)
        db.add(agent)
    agent.enrollment_token_hash = hash_enrollment_token(plaintext_token)
    agent.status = AgentStatus.pending
    db.commit()
    return plaintext_token


@router.post(
    "/servers/{server_id}/enroll-token",
    response_model=EnrollTokenResponse,
    dependencies=[Depends(require_superuser)],
)
def create_enroll_token(
    server_id: uuid.UUID,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    site_ids: list[uuid.UUID] | None = Depends(get_visible_site_ids),
) -> EnrollTokenResponse:
    server = db.get(Server, server_id)
    if server is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Servidor no encontrado")
    _ensure_visible(server, site_ids)

    plaintext_token = _issue_enrollment_token(db, server_id)
    log_action(
        db, current_user, "agent.enroll_token_created", "server", server_id,
        details={"hostname": server.hostname}, request=request,
    )

    return EnrollTokenResponse(server_id=server_id, token=plaintext_token)


@router.get(
    "/servers/{server_id}/installer",
    dependencies=[Depends(require_superuser)],
)
def download_installer(
    server_id: uuid.UUID,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    site_ids: list[uuid.UUID] | None = Depends(get_visible_site_ids),
) -> Response:
    """Generates a fresh enrollment token and bundles it with the agent source, NSSM
    and an unattended PowerShell installer into a per-server ZIP — so setting up a new
    server is "download, extract, run install.bat" instead of the manual copy/venv/
    enroll/nssm sequence documented in the guided install page."""
    server = db.get(Server, server_id)
    if server is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Servidor no encontrado")
    _ensure_visible(server, site_ids)

    plaintext_token = _issue_enrollment_token(db, server_id)
    core_url = str(request.base_url).rstrip("/")

    log_action(
        db, current_user, "agent.installer_downloaded", "server", server_id,
        details={"hostname": server.hostname, "os_type": server.os_type.value}, request=request,
    )

    if server.os_type == OSType.linux:
        archive_bytes = build_agent_installer_targz(
            core_url=core_url, server_id=str(server_id), token=plaintext_token, hostname=server.hostname
        )
        return Response(
            content=archive_bytes,
            media_type="application/gzip",
            headers={"Content-Disposition": f'attachment; filename="citi-agent-{server.hostname}.tar.gz"'},
        )

    zip_bytes = build_agent_installer_zip(
        core_url=core_url, server_id=str(server_id), token=plaintext_token, hostname=server.hostname
    )
    return Response(
        content=zip_bytes,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="citi-agent-{server.hostname}.zip"'},
    )


@router.post("/servers/{server_id}/reconnect", dependencies=[Depends(require_superuser)])
async def reconnect_agent(
    server_id: uuid.UUID,
    db: Session = Depends(get_db),
    site_ids: list[uuid.UUID] | None = Depends(get_visible_site_ids),
) -> dict:
    """Closes this one agent's live connection from Core's side (see AgentHub.close_
    connection) so it reconnects on its own within a few seconds and picks up a newer
    agent version if one is available — a normal "Servidor desconectado"/"reconectado"
    notification pair fires for it, same as a real brief network blip would cause."""
    server = db.get(Server, server_id)
    if server is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Servidor no encontrado")
    _ensure_visible(server, site_ids)
    reconnected = await hub.close_connection(server_id)
    return {"reconnected": reconnected}


@router.post("/reconnect-all", dependencies=[Depends(require_superuser)])
async def reconnect_all_agents() -> dict:
    """Same as reconnect_agent, for every currently-connected agent — the mechanism for
    rolling an agent update out to the whole fleet on demand, instead of waiting for
    each one's next organic reconnect. Deliberately fleet-wide, not site-scoped: this
    is an admin/maintenance action, not a data view. Staggered a few seconds apart so
    24+ servers don't all self-update (file write + self-test subprocess) at the exact
    same instant, and so the resulting disconnect/reconnect emails don't land as one
    single flood."""
    server_ids = list(hub.connections.keys())
    reconnected = 0
    for server_id in server_ids:
        if await hub.close_connection(server_id):
            reconnected += 1
        await asyncio.sleep(3)
    return {"connected": len(server_ids), "reconnected": reconnected}


@router.post("/enroll", response_model=AgentEnrollResponse)
def enroll_agent(payload: AgentEnrollRequest, db: Session = Depends(get_db)) -> AgentEnrollResponse:
    agent = db.scalar(select(Agent).where(Agent.server_id == payload.server_id))
    if agent is None or agent.enrollment_token_hash != hash_enrollment_token(payload.token):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token de enrolamiento inválido")

    agent.status = AgentStatus.active
    agent.enrolled_at = datetime.now(timezone.utc)
    agent.enrollment_token_hash = None
    db.commit()

    return AgentEnrollResponse(agent_id=agent.id, agent_token=create_agent_token(str(agent.id)))


def _services_payload(db: Session, server_id: uuid.UUID) -> list[dict]:
    services = db.scalars(select(Service).where(Service.server_id == server_id))
    return [
        {
            "service_id": str(s.id),
            "control_identifier": s.control_identifier,
            "control_strategy": s.control_strategy.value,
        }
        for s in services
        if s.control_identifier
    ]


@router.websocket("/ws")
async def agent_websocket(websocket: WebSocket, token: str) -> None:
    try:
        payload = decode_token(token)
        if payload.get("type") != "agent":
            raise ValueError("not an agent token")
        agent_id = uuid.UUID(payload["sub"])
    except (JWTError, ValueError, KeyError):
        await websocket.close(code=4401)
        return

    db = SessionLocal()
    server_id: uuid.UUID | None = None
    disconnect_reason = _disconnect_reason(None)  # overwritten in the except branches below
    try:
        agent = db.get(Agent, agent_id)
        if agent is None or agent.status == AgentStatus.revoked:
            await websocket.close(code=4403)
            return
        server_id = agent.server_id
        was_unreachable = agent.status == AgentStatus.unreachable

        await websocket.accept()
        await hub.register(server_id, websocket)
        agent.status = AgentStatus.active
        agent.last_heartbeat_at = datetime.now(timezone.utc)
        server = db.get(Server, server_id)
        if server is not None:
            server.status = ServerStatus.online
        db.commit()

        if was_unreachable and server is not None:
            ip_suffix = f" ({server.ip_address})" if server.ip_address else ""
            await notify_incident(
                db,
                site_id=server.site_id,
                severity="info",
                title=f"Servidor reconectado: {server.hostname}",
                message=f"El Agente CITI del servidor '{server.hostname}'{ip_suffix} se reconectó correctamente.",
                entity_type="server",
                entity_id=server.id,
                email=True,
                server_id=server.id,
            )

        services_payload = _services_payload(db, server_id)
        latest_agent_version = _agent_source_payload()["version"]
        # Closes out the transaction _services_payload's SELECT opened — otherwise it sits
        # idle-in-transaction across the wait for the agent's first heartbeat, up to
        # HEARTBEAT_INTERVAL_SECONDS, right after this connection is established.
        db.commit()

        await websocket.send_json({
            "type": "hello_ack",
            "services": services_payload,
            "latest_agent_version": latest_agent_version,
        })

        while True:
            message = await websocket.receive_json()
            msg_type = message.get("type")

            if msg_type == "heartbeat":
                agent.last_heartbeat_at = datetime.now(timezone.utc)
                metrics = message.get("metrics")
                if metrics:
                    agent.cpu_percent = metrics.get("cpu_percent")
                    agent.ram_total_mb = metrics.get("ram_total_mb")
                    agent.ram_used_mb = metrics.get("ram_used_mb")
                    agent.ram_percent = metrics.get("ram_percent")
                    agent.disks = metrics.get("disks")
                    agent.net_bytes_sent = metrics.get("net_bytes_sent")
                    agent.net_bytes_recv = metrics.get("net_bytes_recv")
                    agent.uptime_seconds = metrics.get("uptime_seconds")
                    agent.metrics_updated_at = agent.last_heartbeat_at
                    agent.net_sent_rate_mbps = metrics.get("net_sent_rate_mbps")
                    agent.net_recv_rate_mbps = metrics.get("net_recv_rate_mbps")
                    agent.disk_read_mbps = metrics.get("disk_read_mbps")
                    agent.disk_write_mbps = metrics.get("disk_write_mbps")
                    agent.disk_io = metrics.get("disk_io")
                    agent.kernel_version = metrics.get("kernel_version")
                    agent.cpu_model = metrics.get("cpu_model")
                    agent.load_average_1m = metrics.get("load_average_1m")
                    if metrics.get("agent_version"):
                        agent.version = metrics.get("agent_version")
                    if metrics.get("processes_updated_at"):
                        agent.top_cpu_processes = metrics.get("top_cpu_processes")
                        agent.top_ram_processes = metrics.get("top_ram_processes")
                        agent.port_connections = metrics.get("port_connections")
                        agent.processes_updated_at = _parse_agent_timestamp(metrics.get("processes_updated_at"))
                    if metrics.get("disk_health") is not None:
                        agent.disk_health = metrics.get("disk_health")

                    # Durable history for review, not alerting — see ServerEvent's docstring.
                    # Existence check is belt-and-suspenders; the unique constraint is the
                    # real backstop against the agent's in-memory watermark resetting on restart.
                    for event in metrics.get("critical_events") or []:
                        occurred_at = _parse_agent_timestamp(event.get("occurred_at")) or agent.last_heartbeat_at
                        exists = db.scalar(
                            select(ServerEvent.id).where(
                                ServerEvent.server_id == server_id,
                                ServerEvent.log_name == event.get("log_name"),
                                ServerEvent.event_record_id == event.get("event_record_id"),
                            )
                        )
                        if exists is None:
                            db.add(
                                ServerEvent(
                                    server_id=server_id,
                                    log_name=event.get("log_name"),
                                    event_record_id=event.get("event_record_id"),
                                    level=event.get("level"),
                                    provider=event.get("provider"),
                                    event_id=event.get("event_id"),
                                    message=event.get("message"),
                                    occurred_at=occurred_at,
                                )
                            )

                    last_history = db.scalar(
                        select(ServerMetricHistory)
                        .where(ServerMetricHistory.server_id == server_id)
                        .order_by(ServerMetricHistory.recorded_at.desc())
                    )
                    if last_history is None or agent.last_heartbeat_at - last_history.recorded_at >= METRIC_HISTORY_INTERVAL:
                        disk_percents = [d.get("percent_used") for d in (metrics.get("disks") or []) if d.get("percent_used") is not None]
                        db.add(
                            ServerMetricHistory(
                                server_id=server_id,
                                cpu_percent=metrics.get("cpu_percent"),
                                ram_percent=metrics.get("ram_percent"),
                                disk_percent_used=max(disk_percents) if disk_percents else None,
                                net_bytes_sent=metrics.get("net_bytes_sent"),
                                net_bytes_recv=metrics.get("net_bytes_recv"),
                            )
                        )

                    # No backend-side throttle needed here — the agent already self-limits
                    # to one cycle every NETWORK_PATH_INTERVAL_SECONDS (60s) and only ever
                    # includes a fresh, not-yet-sent result (see network_path_loop), so this
                    # field is either absent or genuinely new.
                    network_path = metrics.get("network_path")
                    if network_path is not None:
                        db.add(
                            ServerNetworkPathHistory(
                                server_id=server_id,
                                recorded_at=_parse_agent_timestamp(network_path.get("sampled_at")) or agent.last_heartbeat_at,
                                target=network_path.get("target"),
                                reachable=bool(network_path.get("reachable")),
                                hops=network_path.get("hops") or [],
                            )
                        )
                db.commit()

                if metrics:
                    server_for_alert = db.get(Server, server_id)
                    hostname = server_for_alert.hostname if server_for_alert is not None else str(server_id)
                    site_id_for_alert = server_for_alert.site_id if server_for_alert is not None else None
                    alerts = evaluate_metric_alerts(db, server_id, hostname, metrics)
                    # evaluate_metric_alerts only commits when an alert actually opens/closes
                    # — the common case (nothing changed) would otherwise leave this session's
                    # transaction (opened by the db.get() above) sitting idle while the loop
                    # goes back to awaiting the next heartbeat message, up to
                    # HEARTBEAT_INTERVAL_SECONDS later. Committing unconditionally here closes
                    # it out every cycle regardless of which path was taken.
                    db.commit()
                    for alert in alerts:
                        await notify_incident(
                            db,
                            site_id=site_id_for_alert,
                            severity=alert["severity"],
                            title=alert["title"],
                            message=alert["message"],
                            entity_type="server",
                            entity_id=server_id,
                            server_id=server_id,
                        )

            elif msg_type == "request_agent_source":
                await websocket.send_json({"type": "agent_source", **_agent_source_payload()})

            elif msg_type == "result":
                action_log_id = uuid.UUID(message["action_log_id"])
                log = db.get(ServiceActionLog, action_log_id)
                if log is not None:
                    log.status = (
                        ActionResultStatus.success if message.get("status") == "success" else ActionResultStatus.failed
                    )
                    log.output = message.get("output")
                    log.finished_at = datetime.now(timezone.utc)
                # Commit (or, if the row was somehow missing, roll back the read-only
                # SELECT above) unconditionally — otherwise the not-found branch leaves this
                # session's transaction open into the next await ws.receive_json().
                db.commit() if log is not None else db.rollback()
                hub.resolve_result(action_log_id, message)

            elif msg_type == "backup_result":
                backup_run_id = uuid.UUID(message["backup_run_id"])
                run = db.get(BackupRun, backup_run_id)
                if run is not None:
                    run.status = RunStatus.success if message.get("status") == "success" else RunStatus.failed
                    run.size_bytes = message.get("size_bytes")
                    run.sha256_hash = message.get("sha256_hash")
                    run.storage_path = message.get("storage_path")
                    run.error_message = message.get("error")
                    run.finished_at = datetime.now(timezone.utc)
                db.commit() if run is not None else db.rollback()
                hub.resolve_result(backup_run_id, message)

            elif msg_type == "restore_result":
                restore_id = uuid.UUID(message["restore_id"])
                restore = db.get(RestoreOperation, restore_id)
                if restore is not None:
                    restore.status = RunStatus.success if message.get("status") == "success" else RunStatus.failed
                    restore.restored_to_path = message.get("restored_to_path")
                    restore.notes = message.get("error")
                    restore.finished_at = datetime.now(timezone.utc)
                db.commit() if restore is not None else db.rollback()
                hub.resolve_result(restore_id, message)

            elif msg_type == "git_status_result":
                hub.resolve_result(uuid.UUID(message["request_id"]), message)

            elif msg_type == "deploy_result":
                hub.resolve_result(uuid.UUID(message["deployment_id"]), message)

            elif msg_type == "http_check_result":
                hub.resolve_result(uuid.UUID(message["check_id"]), message)

    except WebSocketDisconnect as exc:
        disconnect_reason = _disconnect_reason(exc.code)
    except Exception:
        # Anything else (a bug in message handling, a malformed payload, etc.) would
        # otherwise look identical to a clean disconnect in the notification the tech
        # receives, with no trace of why — log it against this specific server so a
        # real bug is diagnosable instead of looking like unexplained flakiness.
        logger.exception(
            "Excepción no controlada en la conexión de agente (server_id=%s); se reportará como desconexión",
            server_id,
        )
        disconnect_reason = "error inesperado en la comunicación con el agente (revisar logs del backend)"
    finally:
        if server_id is not None:
            hub.disconnect(server_id)
            agent = db.get(Agent, agent_id)
            server = db.get(Server, server_id)
            if agent is not None:
                agent.status = AgentStatus.unreachable
            if server is not None:
                server.status = ServerStatus.offline
            db.commit()
            if server is not None:
                ip_suffix = f" ({server.ip_address})" if server.ip_address else ""
                await notify_incident(
                    db,
                    site_id=server.site_id,
                    severity="critical",
                    title=f"Servidor desconectado: {server.hostname}",
                    message=(
                        f"El Agente CITI del servidor '{server.hostname}'{ip_suffix} se desconectó. "
                        f"Motivo: {disconnect_reason}. "
                        "Los servicios de este servidor no podrán administrarse hasta que se reconecte."
                    ),
                    entity_type="server",
                    entity_id=server.id,
                    email=True,
                    server_id=server.id,
                )
        db.close()
