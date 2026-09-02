import asyncio
import uuid

from fastapi import WebSocket


class AgentHub:
    """In-memory registry of connected CITI Agents and pending command results.

    Single-process only (fine for Phase 1 / one CITI Core instance). A multi-instance
    deployment would need a shared broker (Redis pub/sub) instead of this in-process dict.
    """

    def __init__(self) -> None:
        self.connections: dict[uuid.UUID, WebSocket] = {}
        self.pending_results: dict[uuid.UUID, asyncio.Future] = {}

    def is_connected(self, server_id: uuid.UUID) -> bool:
        return server_id in self.connections

    async def register(self, server_id: uuid.UUID, websocket: WebSocket) -> None:
        self.connections[server_id] = websocket

    def disconnect(self, server_id: uuid.UUID) -> None:
        self.connections.pop(server_id, None)

    async def send_command(self, server_id: uuid.UUID, payload: dict) -> bool:
        websocket = self.connections.get(server_id)
        if websocket is None:
            return False
        await websocket.send_json(payload)
        return True

    async def close_connection(self, server_id: uuid.UUID, code: int = 1000) -> bool:
        """Closes this agent's live connection from Core's side, so it runs its own
        existing reconnect logic and gets a fresh hello_ack (picking up a newer agent
        version if one became available). Works no matter what version the agent is
        currently running — unlike a new command message type, an old agent doesn't
        need to understand anything new to react to its connection dropping, since
        recovering from a dropped connection is already core to how every version
        behaves (real network blips do this to it all the time).

        Also reused by the heartbeat watchdog (app/services/agent_watchdog.py) to force-close
        a connection whose remote end has gone silent without a clean close — passing a
        distinct `code` there lets agents.py's WebSocketDisconnect handler report an accurate
        "motivo" instead of misclassifying it as a normal close. This is a local state
        transition (uvicorn doesn't wait for the remote to ack), so it unblocks the handler's
        blocked receive_json() promptly even if the remote is truly gone, not just idle."""
        websocket = self.connections.get(server_id)
        if websocket is None:
            return False
        await websocket.close(code=code)
        return True

    def create_pending_result(self, action_log_id: uuid.UUID) -> asyncio.Future:
        future: asyncio.Future = asyncio.get_event_loop().create_future()
        self.pending_results[action_log_id] = future
        return future

    def resolve_result(self, action_log_id: uuid.UUID, result: dict) -> None:
        future = self.pending_results.pop(action_log_id, None)
        if future is not None and not future.done():
            future.set_result(result)

    def discard_pending_result(self, action_log_id: uuid.UUID) -> None:
        self.pending_results.pop(action_log_id, None)


hub = AgentHub()
