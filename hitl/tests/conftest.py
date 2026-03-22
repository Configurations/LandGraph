"""Shared test fixtures for the HITL backend."""

from __future__ import annotations

import sys
import uuid
from datetime import datetime, timezone
from typing import Any, AsyncGenerator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient


# ── FakeRecord ──────────────────────────────────────────────────

class FakeRecord(dict):
    """Dict subclass that mimics asyncpg.Record key access."""

    def __getitem__(self, key: Any) -> Any:
        return super().__getitem__(key)

    def get(self, key: Any, default: Any = None) -> Any:
        return super().get(key, default)


def make_record(**kwargs: Any) -> FakeRecord:
    """Build a FakeRecord from keyword arguments."""
    return FakeRecord(**kwargs)


# ── Sample data ─────────────────────────────────────────────────

SAMPLE_USER_ID = uuid.UUID("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")


@pytest.fixture()
def sample_user_row() -> FakeRecord:
    """A complete hitl_users row."""
    return make_record(
        id=SAMPLE_USER_ID,
        email="alice@example.com",
        password_hash="$2b$12$fakehashfakehashfakehashfakehashfakehashfakehashfake",
        display_name="Alice",
        role="member",
        is_active=True,
        auth_type="local",
        culture="fr",
        last_login=datetime(2026, 3, 20, tzinfo=timezone.utc),
    )


# ── Mock pool ───────────────────────────────────────────────────

class _FakeAcquire:
    """Async context manager returned by pool.acquire()."""

    def __init__(self, conn: AsyncMock) -> None:
        self._conn = conn

    async def __aenter__(self) -> AsyncMock:
        return self._conn

    async def __aexit__(self, *args: Any) -> None:
        pass


@pytest.fixture()
def mock_pool() -> AsyncMock:
    """An AsyncMock asyncpg pool with acquire, fetchrow, fetch, execute."""
    pool = AsyncMock()
    conn = AsyncMock()
    pool.acquire.return_value = _FakeAcquire(conn)
    pool.fetchrow = AsyncMock(return_value=None)
    pool.fetch = AsyncMock(return_value=[])
    pool.execute = AsyncMock(return_value="UPDATE 1")
    return pool


# ── Helpers to configure mock returns ───────────────────────────

def set_fetchrow(pool: AsyncMock, value: Any) -> None:
    """Set the return value for pool.fetchrow."""
    pool.fetchrow.return_value = value


def set_fetch(pool: AsyncMock, value: list) -> None:
    """Set the return value for pool.fetch."""
    pool.fetch.return_value = value


# ── App client ──────────────────────────────────────────────────

@pytest_asyncio.fixture()
async def app_client(mock_pool: AsyncMock) -> AsyncGenerator[AsyncClient, None]:
    """httpx AsyncClient wired to the FastAPI app with a mock pool."""
    with (
        patch("core.database._pool", mock_pool),
        patch("core.database.get_pool", return_value=mock_pool),
        patch("core.database.init_pool", new_callable=AsyncMock, return_value=mock_pool),
        patch("core.database.close_pool", new_callable=AsyncMock),
        patch("core.pg_notify.pg_listener.start", new_callable=AsyncMock),
        patch("core.pg_notify.pg_listener.stop", new_callable=AsyncMock),
    ):
        from main import app
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            yield client
