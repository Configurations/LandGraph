"""WebSocket connection manager for real-time broadcasts."""

from __future__ import annotations

from typing import Any

import structlog
from fastapi import WebSocket

log = structlog.get_logger(__name__)


class WebSocketManager:
    """Manages WebSocket connections grouped by team_id."""

    def __init__(self) -> None:
        self._connections: dict[str, set[WebSocket]] = {}

    async def connect(self, team_id: str, websocket: WebSocket) -> None:
        """Register a WebSocket connection for a team."""
        if team_id not in self._connections:
            self._connections[team_id] = set()
        self._connections[team_id].add(websocket)

    async def disconnect(self, team_id: str, websocket: WebSocket) -> None:
        """Unregister a WebSocket connection."""
        if team_id in self._connections:
            self._connections[team_id].discard(websocket)
            if not self._connections[team_id]:
                del self._connections[team_id]

    async def broadcast(
        self, team_id: str, event_type: str, data: Any,
    ) -> None:
        """Send an event to all connections for a specific team."""
        connections = self._connections.get(team_id, set()).copy()
        message = {"type": event_type, "data": data}
        dead: list[WebSocket] = []
        for ws in connections:
            try:
                await ws.send_json(message)
            except Exception:
                dead.append(ws)
        for ws in dead:
            await self.disconnect(team_id, ws)

    async def broadcast_all(self, event_type: str, data: Any) -> None:
        """Send an event to all connected clients across all teams."""
        for team_id in list(self._connections.keys()):
            await self.broadcast(team_id, event_type, data)


# Singleton instance
ws_manager = WebSocketManager()
