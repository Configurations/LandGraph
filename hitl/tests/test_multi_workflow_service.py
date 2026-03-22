"""Tests for services/multi_workflow_service.py — lifecycle, transitions, CRUD."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest

from tests.conftest import FakeRecord, make_record


NOW = datetime(2026, 3, 22, 12, 0, tzinfo=timezone.utc)
NOW_STR = str(NOW)


def _wf_row(**overrides) -> FakeRecord:
    """Build a fake project_workflows row."""
    defaults = dict(
        id=1,
        project_slug="tracker",
        workflow_name="Discovery",
        workflow_type="discovery",
        workflow_json_path="/app/Shared/Projects/saas/discovery.wrk.json",
        status="pending",
        mode="sequential",
        priority=90,
        iteration=1,
        depends_on_workflow_id=None,
        config={},
        started_at=None,
        completed_at=None,
        created_at=NOW_STR,
    )
    defaults.update(overrides)
    return make_record(**defaults)


# ── create_workflow ──────────────────────────────────────────


@pytest.mark.asyncio
@patch("services.multi_workflow_service.fetch_one", new_callable=AsyncMock)
async def test_create_workflow_inserts_and_returns_id(mock_fetch):
    """create_workflow inserts a row and returns a response with the new id."""
    mock_fetch.return_value = _wf_row(id=42)

    from schemas.workflow import ProjectWorkflowCreate
    from services.multi_workflow_service import create_workflow

    data = ProjectWorkflowCreate(
        workflow_name="Discovery",
        workflow_type="discovery",
        workflow_json_path="/path/discovery.wrk.json",
        priority=90,
    )
    result = await create_workflow("tracker", data)

    assert result.id == 42
    assert result.project_slug == "tracker"
    assert result.workflow_name == "Discovery"
    mock_fetch.assert_awaited_once()


# ── activate_workflow ────────────────────────────────────────


@pytest.mark.asyncio
@patch("services.multi_workflow_service.fetch_one", new_callable=AsyncMock)
async def test_activate_workflow_updates_status_and_started_at(mock_fetch):
    """activate_workflow sets status=active and populates started_at."""
    mock_fetch.return_value = _wf_row(status="active", started_at=NOW_STR)

    from services.multi_workflow_service import activate_workflow

    result = await activate_workflow(1)

    assert result is not None
    assert result.status == "active"
    assert result.started_at is not None


@pytest.mark.asyncio
@patch("services.multi_workflow_service.fetch_one", new_callable=AsyncMock)
async def test_activate_workflow_returns_none_when_not_pending(mock_fetch):
    """activate_workflow returns None when the row is not in pending status."""
    mock_fetch.return_value = None

    from services.multi_workflow_service import activate_workflow

    result = await activate_workflow(999)
    assert result is None


# ── complete_workflow ────────────────────────────────────────


@pytest.mark.asyncio
@patch("services.multi_workflow_service.fetch_one", new_callable=AsyncMock)
async def test_complete_workflow_updates_status(mock_fetch):
    """complete_workflow sets status=completed and completed_at."""
    mock_fetch.return_value = _wf_row(
        status="completed", completed_at=NOW_STR,
    )

    from services.multi_workflow_service import complete_workflow

    result = await complete_workflow(1)

    assert result is not None
    assert result.status == "completed"
    assert result.completed_at is not None


# ── check_workflow_transitions ───────────────────────────────


@pytest.mark.asyncio
@patch("services.multi_workflow_service.fetch_all", new_callable=AsyncMock)
async def test_check_transitions_returns_activatable(mock_fetch_all):
    """check_workflow_transitions returns pending workflows whose deps are met."""
    mock_fetch_all.return_value = [
        _wf_row(id=2, workflow_name="Design", depends_on_workflow_id=1),
    ]

    from services.multi_workflow_service import check_workflow_transitions

    result = await check_workflow_transitions("tracker")

    assert len(result) == 1
    assert result[0].id == 2
    assert result[0].workflow_name == "Design"


# ── relaunch_workflow ────────────────────────────────────────


@pytest.mark.asyncio
@patch("services.multi_workflow_service.fetch_one", new_callable=AsyncMock)
async def test_relaunch_workflow_creates_new_iteration(mock_fetch):
    """relaunch_workflow creates a new row with incremented iteration."""
    original = _wf_row(id=1, status="completed", iteration=1, config={})
    relaunched = _wf_row(id=3, status="pending", iteration=2)
    mock_fetch.side_effect = [original, relaunched]

    from services.multi_workflow_service import relaunch_workflow

    result = await relaunch_workflow(1)

    assert result is not None
    assert result.id == 3
    assert result.iteration == 2
    assert result.status == "pending"


@pytest.mark.asyncio
@patch("services.multi_workflow_service.fetch_one", new_callable=AsyncMock)
async def test_relaunch_workflow_returns_none_for_active(mock_fetch):
    """relaunch_workflow returns None if the workflow is still active."""
    mock_fetch.return_value = _wf_row(status="active")

    from services.multi_workflow_service import relaunch_workflow

    result = await relaunch_workflow(1)
    assert result is None


# ── list_workflows ───────────────────────────────────────────


@pytest.mark.asyncio
@patch("services.multi_workflow_service.fetch_all", new_callable=AsyncMock)
async def test_list_workflows_returns_ordered(mock_fetch_all):
    """list_workflows returns all workflows for a project ordered by priority."""
    mock_fetch_all.return_value = [
        _wf_row(id=1, priority=90, workflow_name="Discovery"),
        _wf_row(id=2, priority=70, workflow_name="Design"),
    ]

    from services.multi_workflow_service import list_workflows

    result = await list_workflows("tracker")

    assert len(result) == 2
    assert result[0].workflow_name == "Discovery"
    assert result[1].workflow_name == "Design"


# ── get_active_workflows ─────────────────────────────────────


@pytest.mark.asyncio
@patch("services.multi_workflow_service.fetch_all", new_callable=AsyncMock)
async def test_get_active_workflows_filters_by_status(mock_fetch_all):
    """get_active_workflows only returns workflows with status=active."""
    mock_fetch_all.return_value = [
        _wf_row(id=1, status="active"),
    ]

    from services.multi_workflow_service import get_active_workflows

    result = await get_active_workflows("tracker")

    assert len(result) == 1
    assert result[0].status == "active"
    # Verify the SQL was called with status filter
    call_args = mock_fetch_all.call_args
    assert "active" in call_args.args
