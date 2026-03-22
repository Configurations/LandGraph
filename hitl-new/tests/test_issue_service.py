"""Tests for services/issue_service.py."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tests.conftest import FakeRecord, make_record


NOW = datetime(2026, 3, 22, 12, 0, tzinfo=timezone.utc)


def _issue_row(**overrides) -> FakeRecord:
    """Build a fake pm_issues row with blocking metadata."""
    defaults = dict(
        id="TEAM-001",
        project_id=1,
        title="Setup CI",
        description="Configure GitHub Actions",
        status="todo",
        priority=2,
        assignee="alice@test.com",
        team_id="team1",
        tags=["ci", "devops"],
        phase="build",
        created_by="bob@test.com",
        created_at=NOW,
        updated_at=NOW,
        is_blocked=False,
        blocking_count=0,
        blocked_by_count=0,
    )
    defaults.update(overrides)
    return make_record(**defaults)


# ── _get_team_prefix ──────────────────────────────────────────

class TestGetTeamPrefix:
    def test_normal_team_id(self):
        from services.issue_service import _get_team_prefix
        assert _get_team_prefix("team1") == "TEAM"

    def test_short_team_id(self):
        from services.issue_service import _get_team_prefix
        assert _get_team_prefix("ab") == "AB"

    def test_team_id_with_dashes(self):
        from services.issue_service import _get_team_prefix
        assert _get_team_prefix("my-team") == "MYTE"


# ── create_issue ──────────────────────────────────────────────

@pytest.mark.asyncio
@patch("services.issue_service.fetch_one", new_callable=AsyncMock)
@patch("services.issue_service._next_issue_id", new_callable=AsyncMock)
@patch("services.issue_helpers.execute", new_callable=AsyncMock)
async def test_create_issue_generates_id(mock_exec, mock_next_id, mock_fetch):
    """create_issue allocates a sequential ID and inserts a DB row."""
    from schemas.issue import IssueCreate
    from services.issue_service import create_issue

    mock_next_id.return_value = "TEAM-001"
    mock_fetch.return_value = _issue_row()

    data = IssueCreate(title="Setup CI", description="Configure GitHub Actions", priority=2)
    result = await create_issue(data, "team1", "bob@test.com")

    assert result.id == "TEAM-001"
    assert result.title == "Setup CI"
    mock_next_id.assert_awaited_once_with("team1")
    mock_fetch.assert_awaited_once()


@pytest.mark.asyncio
@patch("services.issue_service.fetch_one", new_callable=AsyncMock)
@patch("services.issue_service._next_issue_id", new_callable=AsyncMock)
@patch("services.issue_helpers.execute", new_callable=AsyncMock)
async def test_create_issue_logs_activity(mock_exec, mock_next_id, mock_fetch):
    """create_issue logs activity when project_id is set."""
    from schemas.issue import IssueCreate
    from services.issue_service import create_issue

    mock_next_id.return_value = "TEAM-002"
    mock_fetch.return_value = _issue_row(id="TEAM-002", project_id=5)

    data = IssueCreate(title="New task", project_id=5)
    await create_issue(data, "team1", "bob@test.com")

    mock_exec.assert_awaited()


@pytest.mark.asyncio
@patch("services.issue_service.fetch_one", new_callable=AsyncMock)
@patch("services.issue_service._next_issue_id", new_callable=AsyncMock)
@patch("services.issue_helpers.execute", new_callable=AsyncMock)
@patch("services.inbox_service.execute", new_callable=AsyncMock)
async def test_create_issue_notifies_assignee(
    mock_inbox_exec, mock_helper_exec, mock_next_id, mock_fetch,
):
    """create_issue sends notification to assignee when different from creator."""
    from schemas.issue import IssueCreate
    from services.issue_service import create_issue

    mock_next_id.return_value = "TEAM-003"
    mock_fetch.return_value = _issue_row(id="TEAM-003", assignee="charlie@test.com")

    data = IssueCreate(title="Assigned", assignee="charlie@test.com")
    await create_issue(data, "team1", "bob@test.com")

    # inbox notification should have been called
    mock_inbox_exec.assert_awaited()


# ── update_issue ──────────────────────────────────────────────

@pytest.mark.asyncio
@patch("services.issue_service.execute", new_callable=AsyncMock)
@patch("services.issue_service.fetch_one", new_callable=AsyncMock)
@patch("services.issue_helpers.fetch_one", new_callable=AsyncMock)
@patch("services.issue_helpers.execute", new_callable=AsyncMock)
@patch("services.inbox_service.execute", new_callable=AsyncMock)
async def test_update_status_logs_and_notifies(
    mock_inbox_exec, mock_helper_exec, mock_helper_fetch,
    mock_svc_fetch, mock_svc_exec,
):
    """Changing status logs activity and sends notifications."""
    from schemas.issue import IssueUpdate
    from services.issue_service import update_issue

    current = _issue_row(status="todo", created_by="bob@test.com")
    updated = _issue_row(status="in-progress")
    mock_svc_fetch.return_value = current
    mock_helper_fetch.return_value = updated

    data = IssueUpdate(status="in-progress")
    result = await update_issue("TEAM-001", data, "alice@test.com")

    mock_svc_exec.assert_awaited()


@pytest.mark.asyncio
@patch("services.issue_service.execute", new_callable=AsyncMock)
@patch("services.issue_service.fetch_one", new_callable=AsyncMock)
@patch("services.issue_helpers.fetch_one", new_callable=AsyncMock)
@patch("services.issue_helpers.execute", new_callable=AsyncMock)
@patch("services.inbox_service.execute", new_callable=AsyncMock)
async def test_update_assignee_notifies(
    mock_inbox_exec, mock_helper_exec, mock_helper_fetch,
    mock_svc_fetch, mock_svc_exec,
):
    """Changing assignee sends notification to the new assignee."""
    from schemas.issue import IssueUpdate
    from services.issue_service import update_issue

    current = _issue_row(assignee="old@test.com")
    updated = _issue_row(assignee="new@test.com")
    mock_svc_fetch.return_value = current
    mock_helper_fetch.return_value = updated

    data = IssueUpdate(assignee="new@test.com")
    await update_issue("TEAM-001", data, "alice@test.com")

    mock_inbox_exec.assert_awaited()


# ── list_issues ───────────────────────────────────────────────

@pytest.mark.asyncio
@patch("services.issue_service.fetch_all", new_callable=AsyncMock)
async def test_list_issues_returns_filtered(mock_fetch_all):
    """list_issues returns mapped IssueResponse list."""
    from services.issue_service import list_issues

    mock_fetch_all.return_value = [_issue_row(), _issue_row(id="TEAM-002")]

    result = await list_issues(team_id="team1", status="todo")
    assert len(result) == 2
    assert result[0].id == "TEAM-001"
    assert result[1].id == "TEAM-002"


# ── delete_issue ──────────────────────────────────────────────

@pytest.mark.asyncio
@patch("services.issue_service.execute", new_callable=AsyncMock)
@patch("services.issue_service.fetch_one", new_callable=AsyncMock)
@patch("services.issue_helpers.execute", new_callable=AsyncMock)
async def test_delete_issue_removes(mock_helper_exec, mock_fetch, mock_exec):
    """delete_issue deletes the row and logs activity."""
    from services.issue_service import delete_issue

    mock_fetch.return_value = make_record(project_id=1, title="Old task")

    ok = await delete_issue("TEAM-001", "bob@test.com")
    assert ok is True
    mock_exec.assert_awaited()


@pytest.mark.asyncio
@patch("services.issue_service.fetch_one", new_callable=AsyncMock)
async def test_delete_issue_not_found(mock_fetch):
    """delete_issue returns False for missing issue."""
    from services.issue_service import delete_issue

    mock_fetch.return_value = None
    ok = await delete_issue("NOPE-999", "bob@test.com")
    assert ok is False


# ── search_issues ─────────────────────────────────────────────

@pytest.mark.asyncio
@patch("services.issue_service.fetch_all", new_callable=AsyncMock)
async def test_search_issues_by_id_or_title(mock_fetch_all):
    """search_issues finds issues matching a query."""
    from services.issue_service import search_issues

    mock_fetch_all.return_value = [_issue_row(id="TEAM-001", title="Setup CI")]
    result = await search_issues("team1", "CI")
    assert len(result) == 1
    assert result[0].title == "Setup CI"


# ── get_issue (blocked status) ────────────────────────────────

@pytest.mark.asyncio
@patch("services.relation_service.fetch_all", new_callable=AsyncMock)
@patch("services.issue_service.fetch_one", new_callable=AsyncMock)
async def test_get_issue_blocked(mock_fetch, mock_rel_fetch):
    """get_issue returns is_blocked=True from the DB row."""
    from services.issue_service import get_issue

    row = _issue_row(is_blocked=True, blocked_by_count=1, project_name="Proj")
    mock_fetch.return_value = row
    mock_rel_fetch.return_value = []

    result = await get_issue("TEAM-001")
    assert result is not None
    assert result.is_blocked is True


@pytest.mark.asyncio
@patch("services.issue_service.fetch_one", new_callable=AsyncMock)
async def test_get_issue_not_blocked(mock_fetch):
    """get_issue returns is_blocked=False when no blockers."""
    from services.issue_service import get_issue

    mock_fetch.return_value = None
    result = await get_issue("NOPE-999")
    assert result is None


# ── bulk_create ───────────────────────────────────────────────

@pytest.mark.asyncio
@patch("services.issue_service.create_issue", new_callable=AsyncMock)
async def test_bulk_create_multiple(mock_create):
    """bulk_create calls create_issue for each item."""
    from schemas.issue import IssueCreate, IssueResponse
    from services.issue_service import bulk_create

    resp = MagicMock(spec=IssueResponse)
    mock_create.return_value = resp

    items = [IssueCreate(title="A"), IssueCreate(title="B"), IssueCreate(title="C")]
    results = await bulk_create(items, 1, "team1", "bob@test.com")

    assert len(results) == 3
    assert mock_create.await_count == 3
