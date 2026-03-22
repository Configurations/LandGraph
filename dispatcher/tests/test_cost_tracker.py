"""Tests for services.cost_tracker — cost recording and aggregation."""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock
from uuid import UUID

from services.cost_tracker import CostTracker
from tests.conftest import make_record


TASK_ID = UUID("11111111-2222-3333-4444-555555555555")


@pytest.fixture
def tracker(mock_pool):
    return CostTracker(pool=mock_pool)


# ── record ───────────────────────────────────────────


class TestRecord:
    @pytest.mark.asyncio
    async def test_updates_task_and_summary(self, tracker, mock_pool):
        await tracker.record(
            task_id=TASK_ID,
            project_slug="perf-tracker",
            team_id="team1",
            phase="build",
            agent_id="lead_dev",
            cost_usd=0.12,
        )

        # Two DB calls: UPDATE task + UPSERT summary
        assert mock_pool.execute.call_count == 2

        # First call: update task cost
        first_call = mock_pool.execute.call_args_list[0]
        assert "dispatcher_tasks" in first_call[0][0]
        assert first_call[0][1] == 0.12
        assert first_call[0][2] == TASK_ID

        # Second call: upsert cost_summary
        second_call = mock_pool.execute.call_args_list[1]
        assert "dispatcher_cost_summary" in second_call[0][0]
        assert "ON CONFLICT" in second_call[0][0]

    @pytest.mark.asyncio
    async def test_no_summary_when_no_project_slug(self, tracker, mock_pool):
        await tracker.record(
            task_id=TASK_ID,
            project_slug=None,
            team_id="team1",
            phase="build",
            agent_id="lead_dev",
            cost_usd=0.05,
        )

        # Only the task UPDATE, no summary UPSERT
        assert mock_pool.execute.call_count == 1
        assert "dispatcher_tasks" in mock_pool.execute.call_args[0][0]

    @pytest.mark.asyncio
    async def test_empty_project_slug_no_summary(self, tracker, mock_pool):
        await tracker.record(
            task_id=TASK_ID,
            project_slug="",
            team_id="team1",
            phase="build",
            agent_id="dev",
            cost_usd=0.01,
        )
        # Empty string is falsy, so only 1 call
        assert mock_pool.execute.call_count == 1

    @pytest.mark.asyncio
    async def test_zero_cost_still_records(self, tracker, mock_pool):
        await tracker.record(
            task_id=TASK_ID,
            project_slug="proj",
            team_id="team1",
            phase="build",
            agent_id="dev",
            cost_usd=0.0,
        )
        # Both calls should happen even with zero cost
        assert mock_pool.execute.call_count == 2


# ── get_project_costs ────────────────────────────────


class TestGetProjectCosts:
    @pytest.mark.asyncio
    async def test_returns_list_of_dicts(self, tracker, mock_pool):
        mock_pool.fetch = AsyncMock(return_value=[
            make_record(
                project_slug="perf-tracker",
                team_id="team1",
                phase="build",
                agent_id="lead_dev",
                total_cost_usd=1.5,
                task_count=10,
                avg_cost_per_task=0.15,
            ),
            make_record(
                project_slug="perf-tracker",
                team_id="team1",
                phase="design",
                agent_id="architect",
                total_cost_usd=0.8,
                task_count=4,
                avg_cost_per_task=0.2,
            ),
        ])

        result = await tracker.get_project_costs("perf-tracker")
        assert len(result) == 2
        assert result[0]["agent_id"] == "lead_dev"
        assert result[1]["total_cost_usd"] == 0.8

    @pytest.mark.asyncio
    async def test_returns_empty_list_when_no_data(self, tracker, mock_pool):
        mock_pool.fetch = AsyncMock(return_value=[])
        result = await tracker.get_project_costs("nonexistent")
        assert result == []

    @pytest.mark.asyncio
    async def test_query_filters_by_slug(self, tracker, mock_pool):
        mock_pool.fetch = AsyncMock(return_value=[])
        await tracker.get_project_costs("my-project")

        sql = mock_pool.fetch.call_args[0][0]
        assert "dispatcher_cost_summary" in sql
        assert mock_pool.fetch.call_args[0][1] == "my-project"
