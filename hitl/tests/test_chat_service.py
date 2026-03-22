"""Tests for services/chat_service.py — history, send, clear."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest

from tests.conftest import make_record

NOW = datetime(2026, 3, 20, tzinfo=timezone.utc)


def _msg_row(**overrides):
    defaults = dict(
        id=1, team_id="team1", agent_id="lead_dev",
        thread_id="hitl-chat-team1-lead_dev",
        sender="alice@t.com", content="Hello", created_at=NOW,
    )
    defaults.update(overrides)
    return make_record(**defaults)


# ── get_history ──────────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_history_returns_messages_in_order():
    rows = [
        _msg_row(id=2, content="Reply", sender="lead_dev"),
        _msg_row(id=1, content="Hello", sender="alice@t.com"),
    ]
    with patch("services.chat_service.fetch_all", new_callable=AsyncMock, return_value=rows):
        from services.chat_service import get_history
        result = await get_history("team1", "lead_dev")
    # reversed in service → chronological
    assert len(result) == 2
    assert result[0].content == "Hello"
    assert result[1].content == "Reply"


# ── send_message ─────────────────────────────────────────────

@pytest.mark.asyncio
async def test_send_message_inserts_and_calls_gateway():
    agent_row = _msg_row(id=3, sender="lead_dev", content="Agent reply")
    with (
        patch("services.chat_service.execute", new_callable=AsyncMock),
        patch("services.chat_service._invoke_agent", new_callable=AsyncMock, return_value="Agent reply"),
        patch("services.chat_service.fetch_one", new_callable=AsyncMock, return_value=agent_row),
    ):
        from services.chat_service import send_message
        result = await send_message("team1", "lead_dev", "alice@t.com", "Hello")
    assert result.content == "Agent reply"
    assert result.sender == "lead_dev"


@pytest.mark.asyncio
async def test_send_message_gateway_down_returns_error():
    error_row = _msg_row(id=4, sender="lead_dev", content="[error: connection refused]")
    with (
        patch("services.chat_service.execute", new_callable=AsyncMock),
        patch("services.chat_service._invoke_agent", new_callable=AsyncMock, return_value="[error: connection refused]"),
        patch("services.chat_service.fetch_one", new_callable=AsyncMock, return_value=error_row),
    ):
        from services.chat_service import send_message
        result = await send_message("team1", "lead_dev", "alice@t.com", "Hello")
    assert "[error:" in result.content


# ── clear_chat ───────────────────────────────────────────────

@pytest.mark.asyncio
async def test_clear_chat_deletes_messages():
    with patch("services.chat_service.execute", new_callable=AsyncMock, return_value="DELETE 5"):
        from services.chat_service import clear_chat
        count = await clear_chat("team1", "lead_dev")
    assert count == 5
