"""PostgreSQL LISTEN/NOTIFY helpers."""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Callable, Coroutine, Optional

import asyncpg

from core.config import settings

log = logging.getLogger(__name__)


async def pg_notify(pool: asyncpg.Pool, channel: str, payload: dict[str, Any]) -> None:
    """Send a PG NOTIFY on the given channel."""
    text = json.dumps(payload, ensure_ascii=False, default=str)
    async with pool.acquire() as conn:
        await conn.execute(f"SELECT pg_notify($1, $2)", channel, text)


class PgNotifyListener:
    """Listens on one or more PG NOTIFY channels via a dedicated connection."""

    def __init__(self) -> None:
        self._conn: Optional[asyncpg.Connection] = None
        self._running = False
        self._handlers: dict[str, list[Callable]] = {}

    async def start(self, channels: list[str]) -> None:
        """Open a dedicated connection and LISTEN on the given channels."""
        self._conn = await asyncpg.connect(dsn=settings.database_uri)
        for ch in channels:
            await self._conn.add_listener(ch, self._on_notify)
        self._running = True
        log.info("PG NOTIFY listener started", extra={"channels": channels})

    async def stop(self) -> None:
        """Close the listener connection."""
        self._running = False
        if self._conn is not None:
            await self._conn.close()
            self._conn = None
        log.info("PG NOTIFY listener stopped")

    def on(self, channel: str, handler: Callable) -> None:
        """Register a handler for a channel."""
        self._handlers.setdefault(channel, []).append(handler)

    def _on_notify(
        self,
        connection: asyncpg.Connection,
        pid: int,
        channel: str,
        payload: str,
    ) -> None:
        """Dispatch notification to registered handlers."""
        try:
            data = json.loads(payload)
        except json.JSONDecodeError:
            data = payload
        handlers = self._handlers.get(channel, [])
        for handler in handlers:
            result = handler(channel, data)
            if asyncio.iscoroutine(result):
                asyncio.create_task(result)


class HitlResponseWaiter:
    """Wait for a specific HITL response by request_id."""

    def __init__(self) -> None:
        self._waiters: dict[str, asyncio.Future] = {}

    def handle_response(self, channel: str, data: Any) -> None:
        """Called by PgNotifyListener when hitl_response fires."""
        if not isinstance(data, dict):
            return
        request_id = str(data.get("request_id", ""))
        if request_id in self._waiters:
            fut = self._waiters[request_id]
            if not fut.done():
                fut.set_result(data)

    async def wait_for(self, request_id: str, timeout: float) -> dict[str, Any]:
        """Block until the response arrives or timeout."""
        loop = asyncio.get_running_loop()
        fut: asyncio.Future[dict[str, Any]] = loop.create_future()
        self._waiters[request_id] = fut
        try:
            return await asyncio.wait_for(fut, timeout=timeout)
        finally:
            self._waiters.pop(request_id, None)
