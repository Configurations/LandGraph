"""Tests for services/pr_service.py — CRUD, merge, diff stats."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest

from tests.conftest import FakeRecord, make_record


NOW = datetime(2026, 3, 22, 12, 0, tzinfo=timezone.utc)


def _pr_row(**overrides) -> FakeRecord:
    """Build a fake pm_pull_requests row."""
    defaults = dict(
        id="PR-ABCD1234",
        title="Add login page",
        author="alice@test.com",
        issue_id="TEAM-001",
        issue_title="Login feature",
        status="pending",
        additions=42,
        deletions=10,
        files=3,
        branch="feat/login",
        remote_url="https://github.com/org/repo/pull/1",
        project_slug="tracker",
        created_at=NOW,
        updated_at=NOW,
        merged_by=None,
        merged_at=None,
    )
    defaults.update(overrides)
    return make_record(**defaults)


# ── list_prs ─────────────────────────────────────────────────


@pytest.mark.asyncio
@patch("services.pr_service.fetch_all", new_callable=AsyncMock)
async def test_list_prs_returns_filtered_list(mock_fetch_all):
    """list_prs returns PRResponse objects filtered by slug and status."""
    mock_fetch_all.return_value = [_pr_row(), _pr_row(id="PR-00000002", status="approved")]

    from services.pr_service import list_prs

    result = await list_prs(project_slug="tracker", status="pending")
    assert len(result) == 2
    assert result[0].id == "PR-ABCD1234"
    assert result[1].status == "approved"

    # Verify query includes both filters
    call_args = mock_fetch_all.call_args
    query = call_args[0][0]
    assert "pr.project_slug" in query
    assert "pr.status" in query


@pytest.mark.asyncio
@patch("services.pr_service.fetch_all", new_callable=AsyncMock)
async def test_list_prs_no_filters(mock_fetch_all):
    """list_prs without filters still returns results."""
    mock_fetch_all.return_value = [_pr_row()]

    from services.pr_service import list_prs

    result = await list_prs()
    assert len(result) == 1


# ── create_pr ────────────────────────────────────────────────


@pytest.mark.asyncio
@patch("services.pr_service.log_activity", new_callable=AsyncMock)
@patch("services.pr_service.create_remote_pr", new_callable=AsyncMock)
@patch("services.pr_service.fetch_one", new_callable=AsyncMock)
async def test_create_pr_inserts_and_logs(mock_fetch_one, mock_remote, mock_log_act):
    """create_pr inserts a row, creates remote PR, and logs activity."""
    mock_remote.return_value = "https://github.com/org/repo/pull/99"
    # First call = INSERT RETURNING, second call = project lookup
    inserted = _pr_row(remote_url="https://github.com/org/repo/pull/99")
    proj_row = make_record(id=1)
    mock_fetch_one.side_effect = [inserted, proj_row]

    from schemas.pr import PRCreate
    from services.pr_service import create_pr

    data = PRCreate(branch="feat/login", title="Add login", project_slug="tracker")
    result = await create_pr(data, "alice@test.com")

    assert result.id == "PR-ABCD1234"
    assert result.remote_url == "https://github.com/org/repo/pull/99"
    mock_log_act.assert_called_once()


# ── update_status ────────────────────────────────────────────


@pytest.mark.asyncio
@patch("services.pr_service.create_notification", new_callable=AsyncMock)
@patch("services.pr_service.get_pr", new_callable=AsyncMock)
@patch("services.pr_service.log_activity", new_callable=AsyncMock)
@patch("services.pr_service.execute", new_callable=AsyncMock)
@patch("services.pr_service.fetch_one", new_callable=AsyncMock)
async def test_update_status_changes_and_notifies(
    mock_fetch_one, mock_exec, mock_log_act, mock_get_pr, mock_notify,
):
    """update_status updates DB, logs activity, and notifies author."""
    current = _pr_row(author="bob@test.com", project_slug="tracker")
    proj_row = make_record(id=1)
    mock_fetch_one.side_effect = [current, proj_row]
    mock_get_pr.return_value = _pr_row(status="approved")

    from schemas.pr import PRStatusUpdate
    from services.pr_service import update_status

    data = PRStatusUpdate(status="approved", comment="LGTM")
    result = await update_status("PR-ABCD1234", data, "alice@test.com")

    assert result is not None
    mock_exec.assert_called_once()
    mock_notify.assert_called_once()


# ── merge_pr ─────────────────────────────────────────────────


@pytest.mark.asyncio
@patch("services.pr_service.os.path.isdir", return_value=False)
@patch("services.pr_service.log_activity", new_callable=AsyncMock)
@patch("services.pr_service.get_pr", new_callable=AsyncMock)
@patch("services.pr_service.execute", new_callable=AsyncMock)
@patch("services.pr_service.fetch_one", new_callable=AsyncMock)
async def test_merge_pr_approved_succeeds(
    mock_fetch_one, mock_exec, mock_get_pr, mock_log_act, mock_isdir,
):
    """merge_pr with approved status updates DB and logs."""
    current = _pr_row(status="approved", project_slug="tracker", branch="feat/login")
    mock_fetch_one.return_value = current
    mock_get_pr.return_value = _pr_row(status="merged")

    from services.pr_service import merge_pr

    result = await merge_pr("PR-ABCD1234", "alice@test.com")
    assert result is not None


@pytest.mark.asyncio
@patch("services.pr_service.fetch_one", new_callable=AsyncMock)
async def test_merge_pr_not_approved_returns_none(mock_fetch_one):
    """merge_pr with changes_requested status returns None."""
    current = _pr_row(status="changes_requested")
    mock_fetch_one.return_value = current

    from services.pr_service import merge_pr

    result = await merge_pr("PR-ABCD1234", "alice@test.com")
    assert result is None
