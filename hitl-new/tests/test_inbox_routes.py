"""Tests for routes/inbox.py — HTTP layer."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient

from core.security import encode_token
from tests.conftest import SAMPLE_USER_ID


NOW = datetime(2026, 3, 22, 12, 0, tzinfo=timezone.utc)

TOKEN = encode_token(str(SAMPLE_USER_ID), "alice@test.com", "member", ["team1"])
AUTH = {"Authorization": f"Bearer {TOKEN}"}


# ── GET /api/pm/inbox ─────────────────────────────────────────

@pytest.mark.asyncio
@patch("services.inbox_service.list_notifications", new_callable=AsyncMock)
async def test_list_inbox_200(mock_list, app_client: AsyncClient):
    from schemas.inbox import NotificationResponse

    mock_list.return_value = [
        NotificationResponse(
            id=1, user_email="alice@test.com", type="assign",
            text="assigned to you", read=False, created_at=NOW,
        ),
    ]

    resp = await app_client.get("/api/pm/inbox", headers=AUTH)
    assert resp.status_code == 200
    assert len(resp.json()) == 1


# ── PUT /api/pm/inbox/{id}/read ───────────────────────────────

@pytest.mark.asyncio
@patch("services.inbox_service.mark_read", new_callable=AsyncMock)
async def test_mark_read_200(mock_mark, app_client: AsyncClient):
    mock_mark.return_value = True

    resp = await app_client.put("/api/pm/inbox/1/read", headers=AUTH)
    assert resp.status_code == 200
    assert resp.json()["ok"] is True


@pytest.mark.asyncio
@patch("services.inbox_service.mark_read", new_callable=AsyncMock)
async def test_mark_read_404(mock_mark, app_client: AsyncClient):
    mock_mark.return_value = False

    resp = await app_client.put("/api/pm/inbox/999/read", headers=AUTH)
    assert resp.status_code == 404


# ── PUT /api/pm/inbox/read-all ────────────────────────────────

@pytest.mark.asyncio
@patch("services.inbox_service.mark_all_read", new_callable=AsyncMock)
async def test_mark_all_read_200(mock_mark, app_client: AsyncClient):
    mock_mark.return_value = 3

    resp = await app_client.put("/api/pm/inbox/read-all", headers=AUTH)
    assert resp.status_code == 200
    assert resp.json()["count"] == 3


# ── GET /api/pm/inbox/count ───────────────────────────────────

@pytest.mark.asyncio
@patch("services.inbox_service.get_unread_count", new_callable=AsyncMock)
async def test_unread_count_200(mock_count, app_client: AsyncClient):
    mock_count.return_value = 7

    resp = await app_client.get("/api/pm/inbox/count", headers=AUTH)
    assert resp.status_code == 200
    assert resp.json()["count"] == 7
