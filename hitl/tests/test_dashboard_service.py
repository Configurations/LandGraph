"""Tests for services/dashboard_service.py — active tasks, costs, overview."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from tests.conftest import make_record


# ── get_active_tasks ─────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_active_tasks_returns_list():
    fake_tasks = [
        {"task_id": "1", "agent_id": "lead_dev", "team_id": "team1", "status": "running"},
        {"task_id": "2", "agent_id": "qa_engineer", "team_id": "team1", "status": "running"},
    ]
    mock_resp = MagicMock()
    mock_resp.json.return_value = fake_tasks
    mock_resp.raise_for_status = MagicMock()

    with patch("services.dashboard_service.httpx.AsyncClient") as MockClient:
        ctx = AsyncMock()
        ctx.get.return_value = mock_resp
        MockClient.return_value.__aenter__ = AsyncMock(return_value=ctx)
        MockClient.return_value.__aexit__ = AsyncMock(return_value=False)

        from services.dashboard_service import get_active_tasks
        result = await get_active_tasks()
    assert len(result) == 2
    assert result[0]["agent_id"] == "lead_dev"


@pytest.mark.asyncio
async def test_get_active_tasks_dispatcher_down():
    with patch("services.dashboard_service.httpx.AsyncClient") as MockClient:
        ctx = AsyncMock()
        ctx.get.side_effect = httpx.ConnectError("refused")
        MockClient.return_value.__aenter__ = AsyncMock(return_value=ctx)
        MockClient.return_value.__aexit__ = AsyncMock(return_value=False)

        from services.dashboard_service import get_active_tasks
        result = await get_active_tasks()
    assert result == []


# ── get_project_costs ────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_project_costs_returns_costs():
    fake_costs = {"total": 1.25, "by_phase": {"Discovery": 0.75, "Design": 0.50}}
    mock_resp = MagicMock()
    mock_resp.json.return_value = fake_costs
    mock_resp.raise_for_status = MagicMock()

    with patch("services.dashboard_service.httpx.AsyncClient") as MockClient:
        ctx = AsyncMock()
        ctx.get.return_value = mock_resp
        MockClient.return_value.__aenter__ = AsyncMock(return_value=ctx)
        MockClient.return_value.__aexit__ = AsyncMock(return_value=False)

        from services.dashboard_service import get_project_costs
        result = await get_project_costs("demo")
    assert result["total"] == 1.25


@pytest.mark.asyncio
async def test_get_project_costs_dispatcher_down():
    with patch("services.dashboard_service.httpx.AsyncClient") as MockClient:
        ctx = AsyncMock()
        ctx.get.side_effect = httpx.ConnectError("refused")
        MockClient.return_value.__aenter__ = AsyncMock(return_value=ctx)
        MockClient.return_value.__aexit__ = AsyncMock(return_value=False)

        from services.dashboard_service import get_project_costs
        result = await get_project_costs("demo")
    assert result is None


# ── get_overview ─────────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_overview_aggregates_stats():
    pending_row = make_record(cnt=3)
    cost_row = make_record(total=2.50)

    with (
        patch("services.dashboard_service.fetch_one", new_callable=AsyncMock, side_effect=[pending_row, cost_row]),
        patch("services.dashboard_service.get_active_tasks", new_callable=AsyncMock, return_value=[{"id": 1}, {"id": 2}]),
    ):
        from services.dashboard_service import get_overview
        result = await get_overview("team1", ["team1"])
    assert result["pending_questions"] == 3
    assert result["active_tasks"] == 2
    assert result["total_cost"] == 2.50
