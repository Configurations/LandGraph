"""Tests for WebSocket route (routes/ws.py)."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from core.security import encode_token
from tests.conftest import SAMPLE_USER_ID


MEMBER_TOKEN = encode_token(str(SAMPLE_USER_ID), "m@t.com", "member", ["team1"])
ADMIN_TOKEN = encode_token(str(SAMPLE_USER_ID), "a@t.com", "admin", [])


def _get_app():
    """Import app inside patches to avoid lifespan DB calls."""
    from main import app
    return app


# ── WebSocket tests using httpx + starlette TestClient ─────────

@pytest.mark.asyncio
async def test_ws_invalid_jwt(mock_pool: AsyncMock):
    """Connection with invalid JWT should be closed with 4001."""
    with (
        patch("core.database._pool", mock_pool),
        patch("core.database.get_pool", return_value=mock_pool),
        patch("core.database.init_pool", new_callable=AsyncMock, return_value=mock_pool),
        patch("core.database.close_pool", new_callable=AsyncMock),
        patch("core.database.execute", mock_pool.execute),
        patch("core.database.fetch_one", mock_pool.fetchrow),
        patch("core.database.fetch_all", mock_pool.fetch),
        patch("core.pg_notify.pg_listener.start", new_callable=AsyncMock),
        patch("core.pg_notify.pg_listener.stop", new_callable=AsyncMock),
    ):
        from starlette.testclient import TestClient
        app = _get_app()
        client = TestClient(app)
        with pytest.raises(Exception):
            with client.websocket_connect("/api/teams/team1/ws?token=bad-token"):
                pass


@pytest.mark.asyncio
async def test_ws_forbidden_team(mock_pool: AsyncMock):
    """Member connecting to a team they don't belong to should be closed with 4003."""
    token = encode_token(str(SAMPLE_USER_ID), "m@t.com", "member", ["team2"])

    with (
        patch("core.database._pool", mock_pool),
        patch("core.database.get_pool", return_value=mock_pool),
        patch("core.database.init_pool", new_callable=AsyncMock, return_value=mock_pool),
        patch("core.database.close_pool", new_callable=AsyncMock),
        patch("core.database.execute", mock_pool.execute),
        patch("core.database.fetch_one", mock_pool.fetchrow),
        patch("core.database.fetch_all", mock_pool.fetch),
        patch("core.pg_notify.pg_listener.start", new_callable=AsyncMock),
        patch("core.pg_notify.pg_listener.stop", new_callable=AsyncMock),
    ):
        from starlette.testclient import TestClient
        app = _get_app()
        client = TestClient(app)
        with pytest.raises(Exception):
            with client.websocket_connect(f"/api/teams/team1/ws?token={token}"):
                pass


@pytest.mark.asyncio
async def test_ws_valid_connect(mock_pool: AsyncMock):
    """Valid JWT + authorized team should accept the connection."""
    with (
        patch("core.database._pool", mock_pool),
        patch("core.database.get_pool", return_value=mock_pool),
        patch("core.database.init_pool", new_callable=AsyncMock, return_value=mock_pool),
        patch("core.database.close_pool", new_callable=AsyncMock),
        patch("core.database.execute", mock_pool.execute),
        patch("core.database.fetch_one", mock_pool.fetchrow),
        patch("core.database.fetch_all", mock_pool.fetch),
        patch("core.pg_notify.pg_listener.start", new_callable=AsyncMock),
        patch("core.pg_notify.pg_listener.stop", new_callable=AsyncMock),
    ):
        from starlette.testclient import TestClient
        app = _get_app()
        client = TestClient(app)
        with client.websocket_connect(f"/api/teams/team1/ws?token={MEMBER_TOKEN}") as ws:
            # Connection accepted; send a text message to exercise the receive loop
            ws.send_text("hello")
            # The server listens for text, so we just verify no crash
            ws.close()


@pytest.mark.asyncio
async def test_ws_admin_any_team(mock_pool: AsyncMock):
    """Admin can connect to any team."""
    with (
        patch("core.database._pool", mock_pool),
        patch("core.database.get_pool", return_value=mock_pool),
        patch("core.database.init_pool", new_callable=AsyncMock, return_value=mock_pool),
        patch("core.database.close_pool", new_callable=AsyncMock),
        patch("core.database.execute", mock_pool.execute),
        patch("core.database.fetch_one", mock_pool.fetchrow),
        patch("core.database.fetch_all", mock_pool.fetch),
        patch("core.pg_notify.pg_listener.start", new_callable=AsyncMock),
        patch("core.pg_notify.pg_listener.stop", new_callable=AsyncMock),
    ):
        from starlette.testclient import TestClient
        app = _get_app()
        client = TestClient(app)
        with client.websocket_connect(f"/api/teams/any-team/ws?token={ADMIN_TOKEN}") as ws:
            ws.close()
