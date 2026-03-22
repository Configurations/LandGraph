"""Tests for services/activity_service.py."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest

from tests.conftest import make_record


NOW = datetime(2026, 3, 22, 12, 0, tzinfo=timezone.utc)
EARLIER = datetime(2026, 3, 22, 11, 0, tzinfo=timezone.utc)


# ── log_activity ──────────────────────────────────────────────

@pytest.mark.asyncio
@patch("services.activity_service.execute", new_callable=AsyncMock)
async def test_log_activity_inserts(mock_exec):
    """log_activity inserts a row into pm_activity."""
    from services.activity_service import log_activity

    await log_activity(1, "bob@test.com", "issue_created", "TEAM-001", "Setup CI")
    mock_exec.assert_awaited_once()
    args = mock_exec.call_args
    assert args[0][1] == 1  # project_id
    assert args[0][2] == "bob@test.com"


# ── list_activity ─────────────────────────────────────────────

@pytest.mark.asyncio
@patch("services.activity_service.fetch_all", new_callable=AsyncMock)
async def test_list_activity_ordered(mock_fetch):
    """list_activity returns entries newest first."""
    from services.activity_service import list_activity

    mock_fetch.return_value = [
        make_record(id=2, project_id=1, user_name="alice", action="issue_created",
                    issue_id="TEAM-002", detail="desc", created_at=NOW),
        make_record(id=1, project_id=1, user_name="bob", action="issue_deleted",
                    issue_id="TEAM-001", detail=None, created_at=EARLIER),
    ]

    result = await list_activity(1)
    assert len(result) == 2
    assert result[0].id == 2
    assert result[0].source == "pm"


# ── get_merged_activity ───────────────────────────────────────

@pytest.mark.asyncio
@patch("services.activity_service.fetch_one", new_callable=AsyncMock)
@patch("services.activity_service.fetch_all", new_callable=AsyncMock)
async def test_get_merged_activity_combines(mock_fetch_all, mock_fetch_one):
    """get_merged_activity merges PM and agent entries sorted by time."""
    from services.activity_service import get_merged_activity

    pm_rows = [
        make_record(id=1, project_id=1, user_name="alice", action="issue_created",
                    issue_id="TEAM-001", detail="x", created_at=EARLIER),
    ]
    agent_rows = [
        make_record(id=10, action="agent_complete", user_name="lead_dev",
                    detail="finished", created_at=NOW),
    ]

    # First call: pm_activity, second: dispatcher events
    mock_fetch_all.side_effect = [pm_rows, agent_rows]
    mock_fetch_one.return_value = make_record(slug="perf-tracker")

    result = await get_merged_activity(1, "team1")
    assert len(result) == 2
    # Agent entry is newer, so it comes first
    assert result[0].source == "agent"
    assert result[1].source == "pm"


@pytest.mark.asyncio
@patch("services.activity_service.fetch_one", new_callable=AsyncMock)
@patch("services.activity_service.fetch_all", new_callable=AsyncMock)
async def test_get_merged_activity_no_slug(mock_fetch_all, mock_fetch_one):
    """get_merged_activity works even when project has no slug."""
    from services.activity_service import get_merged_activity

    pm_rows = [
        make_record(id=1, project_id=1, user_name="alice", action="issue_created",
                    issue_id="TEAM-001", detail=None, created_at=NOW),
    ]
    mock_fetch_all.return_value = pm_rows
    mock_fetch_one.return_value = make_record(slug=None)

    result = await get_merged_activity(1, "team1")
    assert len(result) == 1
    assert result[0].source == "pm"
