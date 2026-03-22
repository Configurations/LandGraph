"""Tests for services/inbox_service.py."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest

from tests.conftest import make_record


NOW = datetime(2026, 3, 22, 12, 0, tzinfo=timezone.utc)


def _notif_row(**overrides) -> dict:
    defaults = dict(
        id=1, user_email="alice@test.com", type="assign",
        text="bob assigned TEAM-001 to you", issue_id="TEAM-001",
        related_issue_id=None, relation_type=None, avatar=None,
        read=False, created_at=NOW,
    )
    defaults.update(overrides)
    return make_record(**defaults)


# ── list_notifications ────────────────────────────────────────

@pytest.mark.asyncio
@patch("services.inbox_service.fetch_all", new_callable=AsyncMock)
async def test_list_notifications_ordered(mock_fetch_all):
    """Returns notifications newest first."""
    from services.inbox_service import list_notifications

    mock_fetch_all.return_value = [_notif_row(id=2), _notif_row(id=1)]
    result = await list_notifications("alice@test.com")
    assert len(result) == 2
    assert result[0].id == 2


# ── mark_read ─────────────────────────────────────────────────

@pytest.mark.asyncio
@patch("services.inbox_service.execute", new_callable=AsyncMock)
async def test_mark_read_success(mock_exec):
    """mark_read returns True on successful update."""
    from services.inbox_service import mark_read

    mock_exec.return_value = "UPDATE 1"
    ok = await mark_read(1, "alice@test.com")
    assert ok is True


@pytest.mark.asyncio
@patch("services.inbox_service.execute", new_callable=AsyncMock)
async def test_mark_read_not_found(mock_exec):
    """mark_read returns False when no rows updated."""
    from services.inbox_service import mark_read

    mock_exec.return_value = "UPDATE 0"
    ok = await mark_read(999, "alice@test.com")
    assert ok is False


# ── mark_all_read ─────────────────────────────────────────────

@pytest.mark.asyncio
@patch("services.inbox_service.execute", new_callable=AsyncMock)
async def test_mark_all_read_count(mock_exec):
    """mark_all_read returns the count of updated rows."""
    from services.inbox_service import mark_all_read

    mock_exec.return_value = "UPDATE 5"
    count = await mark_all_read("alice@test.com")
    assert count == 5


# ── get_unread_count ──────────────────────────────────────────

@pytest.mark.asyncio
@patch("services.inbox_service.fetch_one", new_callable=AsyncMock)
async def test_get_unread_count(mock_fetch):
    """get_unread_count returns the count from DB."""
    from services.inbox_service import get_unread_count

    mock_fetch.return_value = make_record(cnt=3)
    count = await get_unread_count("alice@test.com")
    assert count == 3


# ── create_notification ───────────────────────────────────────

@pytest.mark.asyncio
@patch("services.inbox_service.execute", new_callable=AsyncMock)
async def test_create_notification_inserts(mock_exec):
    """create_notification inserts a row into pm_inbox."""
    from services.inbox_service import create_notification

    await create_notification(
        "alice@test.com", "blocked", "TEAM-001 blocked",
        issue_id="TEAM-002", related_issue_id="TEAM-001",
        relation_type="blocks",
    )
    mock_exec.assert_awaited_once()
