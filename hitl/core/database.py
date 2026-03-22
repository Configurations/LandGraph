"""Async PostgreSQL connection pool using asyncpg."""

from __future__ import annotations

from typing import Any, Optional

import asyncpg
import structlog

from core.config import settings

log = structlog.get_logger(__name__)

_pool: Optional[asyncpg.Pool] = None


async def init_pool() -> asyncpg.Pool:
    """Create the connection pool. Called once at startup."""
    global _pool
    if _pool is not None:
        return _pool
    _pool = await asyncpg.create_pool(
        dsn=settings.database_uri,
        min_size=settings.db_pool_min,
        max_size=settings.db_pool_max,
        command_timeout=30,
    )
    log.info(
        "database_pool_created",
        min_size=settings.db_pool_min,
        max_size=settings.db_pool_max,
    )
    return _pool


async def close_pool() -> None:
    """Close the pool. Called at shutdown."""
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None
        log.info("database_pool_closed")


def get_pool() -> asyncpg.Pool:
    """Return the current pool. Raises if not initialised."""
    if _pool is None:
        raise RuntimeError("Database pool not initialised — call init_pool() first")
    return _pool


async def execute(query: str, *args: Any) -> str:
    """Execute a query and return the status string."""
    pool = get_pool()
    return await pool.execute(query, *args)


async def fetch_one(query: str, *args: Any) -> Optional[asyncpg.Record]:
    """Fetch a single row."""
    pool = get_pool()
    return await pool.fetchrow(query, *args)


async def fetch_all(query: str, *args: Any) -> list[asyncpg.Record]:
    """Fetch all rows."""
    pool = get_pool()
    return await pool.fetch(query, *args)


async def get_listen_connection() -> asyncpg.Connection:
    """Get a dedicated connection for LISTEN/NOTIFY (not from the pool)."""
    conn = await asyncpg.connect(dsn=settings.database_uri)
    return conn
