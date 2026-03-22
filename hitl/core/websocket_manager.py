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
        self._watched: dict[WebSocket, set[str]] = {}
        self._user_emails: dict[WebSocket, str] = {}

    async def connect(
        self, team_id: str, websocket: WebSocket, user_email: str = "",
    ) -> None:
        """Register a WebSocket connection for a team."""
        if team_id not in self._connections:
            self._connections[team_id] = set()
        self._connections[team_id].add(websocket)
        if user_email:
            self._user_emails[websocket] = user_email

    async def disconnect(self, team_id: str, websocket: WebSocket) -> None:
        """Unregister a WebSocket connection."""
        if team_id in self._connections:
            self._connections[team_id].discard(websocket)
            if not self._connections[team_id]:
                del self._connections[team_id]
        self._watched.pop(websocket, None)
        self._user_emails.pop(websocket, None)

    def watch_chat(self, websocket: WebSocket, agent_id: str) -> None:
        """Subscribe a WS client to chat events for a specific agent."""
        if websocket not in self._watched:
            self._watched[websocket] = set()
        self._watched[websocket].add(agent_id)

    def unwatch_chat(self, websocket: WebSocket) -> None:
        """Remove all chat subscriptions for a WS client."""
        self._watched.pop(websocket, None)

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

    async def broadcast_watched(
        self, team_id: str, agent_id: str, event_type: str, data: Any,
    ) -> None:
        """Send a chat event only to clients watching this agent."""
        connections = self._connections.get(team_id, set()).copy()
        message = {"type": event_type, "data": data}
        dead: list[WebSocket] = []
        for ws in connections:
            watched = self._watched.get(ws, set())
            if agent_id not in watched:
                continue
            try:
                await ws.send_json(message)
            except Exception:
                dead.append(ws)
        for ws in dead:
            await self.disconnect(team_id, ws)

    async def broadcast_to_user(
        self, user_email: str, event_type: str, data: Any,
    ) -> None:
        """Send an event to all connections belonging to a specific user."""
        message = {"type": event_type, "data": data}
        dead: list[tuple[str, WebSocket]] = []
        for team_id, connections in self._connections.items():
            for ws in connections.copy():
                if self._user_emails.get(ws) != user_email:
                    continue
                try:
                    await ws.send_json(message)
                except Exception:
                    dead.append((team_id, ws))
        for team_id, ws in dead:
            await self.disconnect(team_id, ws)

    async def broadcast_all(self, event_type: str, data: Any) -> None:
        """Send an event to all connected clients across all teams."""
        for team_id in list(self._connections.keys()):
            await self.broadcast(team_id, event_type, data)


# Singleton instance
ws_manager = WebSocketManager()
