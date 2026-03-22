"""Tests for routes/chat.py — chat CRUD endpoints."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient

from core.security import encode_token
from schemas.chat import ChatMessageResponse
from tests.conftest import SAMPLE_USER_ID

TOKEN = encode_token(str(SAMPLE_USER_ID), "alice@t.com", "member", ["team1"])
HEADERS = {"Authorization": f"Bearer {TOKEN}"}

NOW = datetime(2026, 3, 20, tzinfo=timezone.utc)


def _msg(**kw) -> ChatMessageResponse:
    defaults = dict(
        id=1, team_id="team1", agent_id="lead_dev",
        thread_id="hitl-chat-team1-lead_dev",
        sender="alice@t.com", content="Hello", created_at=NOW,
    )
    defaults.update(kw)
    return ChatMessageResponse(**defaults)


# ── GET /api/teams/{id}/agents/{id}/chat ─────────────────────

@pytest.mark.asyncio
async def test_get_chat_history_200(app_client: AsyncClient):
    items = [_msg(id=1), _msg(id=2, sender="lead_dev", content="Hi")]
    with patch("routes.chat.chat_service.get_history", new_callable=AsyncMock, return_value=items):
        resp = await app_client.get(
            "/api/teams/team1/agents/lead_dev/chat", headers=HEADERS,
        )
    assert resp.status_code == 200
    assert len(resp.json()) == 2


# ── POST /api/teams/{id}/agents/{id}/chat ────────────────────

@pytest.mark.asyncio
async def test_send_message_200(app_client: AsyncClient):
    reply = _msg(id=3, sender="lead_dev", content="Agent reply")
    with patch("routes.chat.chat_service.send_message", new_callable=AsyncMock, return_value=reply):
        resp = await app_client.post(
            "/api/teams/team1/agents/lead_dev/chat",
            json={"message": "Hello agent"},
            headers=HEADERS,
        )
    assert resp.status_code == 200
    assert resp.json()["content"] == "Agent reply"


# ── DELETE /api/teams/{id}/agents/{id}/chat ──────────────────

@pytest.mark.asyncio
async def test_clear_chat_200(app_client: AsyncClient):
    with patch("routes.chat.chat_service.clear_chat", new_callable=AsyncMock, return_value=5):
        resp = await app_client.delete(
            "/api/teams/team1/agents/lead_dev/chat", headers=HEADERS,
        )
    assert resp.status_code == 200
    assert resp.json()["deleted"] == 5
