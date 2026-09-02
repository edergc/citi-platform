"""Backstop for connectivity detection: the WebSocket handler in app/api/v1/agents.py
only marks a server offline when its `finally` block runs, which depends on
WebSocketDisconnect actually being raised — that, in turn, depends on the OS/network
stack noticing the TCP connection is gone. A cable pull, power loss, or silent firewall
drop can leave a connection looking "alive" to Python indefinitely, since nothing is
arriving to fail on.

This loop is the fix: any agent whose last_heartbeat_at is older than
STALE_THRESHOLD_SECONDS gets its connection force-closed via hub.close_connection with a
distinct close code, which unblocks the handler's own receive_json() and runs the exact
same offline-marking + notify_incident path a real disconnect would — no duplicated
logic, no separate "half-offline" state to keep in sync.
"""

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.agent_hub import hub
from app.models.infrastructure import Agent, AgentStatus

logger = logging.getLogger("citi.agent_watchdog")

# Agents heartbeat every 15s (see HEARTBEAT_INTERVAL_SECONDS in agent/citi_agent.py) — 4x
# that plus slack for backend load/GC pauses, so a healthy agent under normal jitter is
# never falsely flagged.
STALE_THRESHOLD_SECONDS = 60
_HEARTBEAT_TIMEOUT_CLOSE_CODE = 4408


async def close_stale_agent_connections(db: Session) -> int:
    cutoff = datetime.now(timezone.utc) - timedelta(seconds=STALE_THRESHOLD_SECONDS)
    stale_agent_ids = list(
        db.scalars(
            select(Agent.server_id).where(
                Agent.status == AgentStatus.active,
                Agent.last_heartbeat_at.isnot(None),
                Agent.last_heartbeat_at < cutoff,
            )
        )
    )
    closed = 0
    for server_id in stale_agent_ids:
        # hub.close_connection is a no-op (returns False) if this server already
        # disconnected cleanly between the query above and this call — the real
        # WebSocketDisconnect handler already ran in that case, nothing more to do here.
        if await hub.close_connection(server_id, code=_HEARTBEAT_TIMEOUT_CLOSE_CODE):
            closed += 1
    return closed
