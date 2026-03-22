"""PostgreSQL LISTEN/NOTIFY listener for real-time HITL events."""

from __future__ import annotations

import asyncio
import json
from typing import Any, Optional

import asyncpg
import structlog

from core.config import settings
from core.websocket_manager import WebSocketManager

log = structlog.get_logger(__name__)


class PgNotifyListener:
    """Listens on PG NOTIFY channels and broadcasts to WebSocket clients."""

    def __init__(self) -> None:
        self._conn: Optional[asyncpg.Connection] = None
        self._running: bool = False
        self._ws_manager: Optional[WebSocketManager] = None

    async def start(self, ws_manager: WebSocketManager) -> None:
        """Open a dedicated connection and LISTEN on HITL channels."""
        self._ws_manager = ws_manager
        self._conn = await asyncpg.connect(dsn=settings.database_uri)

        channels = ["hitl_request", "hitl_response"]
        for ch in channels:
            await self._conn.add_listener(ch, self._on_notify)

        self._running = True
        log.info("pg_notify_listener_started", channels=channels)

    async def stop(self) -> None:
        """Close the listener connection."""
        self._running = False
        if self._conn is not None:
            try:
                await self._conn.close()
            except Exception:
                pass
            self._conn = None
        log.info("pg_notify_listener_stopped")

    def _on_notify(
        self,
        connection: asyncpg.Connection,
        pid: int,
        channel: str,
        payload: str,
    ) -> None:
        """Dispatch PG notification to WebSocket clients."""
        try:
            data = json.loads(payload)
        except (json.JSONDecodeError, TypeError):
            data = {"raw": payload}

        if self._ws_manager is None:
            return

        team_id = data.get("team_id", "")
        if not team_id:
            return

        if channel == "hitl_request":
            event_type = "new_question"
        elif channel == "hitl_response":
            event_type = "question_answered"
        else:
            event_type = channel

        coro = self._ws_manager.broadcast(team_id, event_type, data)
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(coro)
        except RuntimeError:
            pass


# Singleton instance
pg_listener = PgNotifyListener()
