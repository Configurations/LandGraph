"""Tests for services/pulse_service.py — metrics aggregation."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest

from tests.conftest import FakeRecord, make_record


NOW = datetime(2026, 3, 22, 12, 0, tzinfo=timezone.utc)


# ── _status_distribution ─────────────────────────────────────


@pytest.mark.asyncio
@patch("services.pulse_service.fetch_all", new_callable=AsyncMock)
async def test_status_distribution_counts_by_status(mock_fetch_all):
    """_status_distribution returns a dict of status -> count."""
    mock_fetch_all.return_value = [
        make_record(status="todo", cnt=5),
        make_record(status="in-progress", cnt=3),
        make_record(status="done", cnt=10),
    ]

    from services.pulse_service import _status_distribution

    result = await _status_distribution(team_id="team1", project_id=None)
    assert result == {"todo": 5, "in-progress": 3, "done": 10}


@pytest.mark.asyncio
@patch("services.pulse_service.fetch_all", new_callable=AsyncMock)
async def test_status_distribution_empty(mock_fetch_all):
    """_status_distribution returns empty dict when no issues."""
    mock_fetch_all.return_value = []

    from services.pulse_service import _status_distribution

    result = await _status_distribution(team_id=None, project_id=None)
    assert result == {}


# ── _velocity ────────────────────────────────────────────────


@pytest.mark.asyncio
@patch("services.pulse_service.fetch_one", new_callable=AsyncMock)
async def test_velocity_done_in_7_days(mock_fetch_one):
    """_velocity returns count of issues done in last 7 days."""
    mock_fetch_one.return_value = make_record(cnt=12)

    from services.pulse_service import _velocity

    result = await _velocity(team_id="team1", project_id=None)
    assert result.value == "12"
    assert "7 days" in result.sub


# ── _throughput ──────────────────────────────────────────────


@pytest.mark.asyncio
@patch("services.pulse_service.fetch_one", new_callable=AsyncMock)
async def test_throughput_avg_per_week(mock_fetch_one):
    """_throughput returns average completed per week over 30 days."""
    mock_fetch_one.return_value = make_record(cnt=20)

    from services.pulse_service import _throughput

    result = await _throughput(team_id=None, project_id=1)
    # 20 issues / 4 weeks = 5.0
    assert result.value == "5.0"
    assert "per week" in result.sub


# ── _cycle_time ──────────────────────────────────────────────


@pytest.mark.asyncio
@patch("services.pulse_service.fetch_one", new_callable=AsyncMock)
async def test_cycle_time_average_days(mock_fetch_one):
    """_cycle_time returns average hours from creation to done."""
    # 2 days in seconds = 172800
    mock_fetch_one.return_value = make_record(avg_secs=172800.0)

    from services.pulse_service import _cycle_time

    result = await _cycle_time(team_id=None, project_id=None)
    assert result.value == "48.0h"
    assert "avg" in result.sub


@pytest.mark.asyncio
@patch("services.pulse_service.fetch_one", new_callable=AsyncMock)
async def test_cycle_time_no_data(mock_fetch_one):
    """_cycle_time returns 0h when no completed issues."""
    mock_fetch_one.return_value = make_record(avg_secs=None)

    from services.pulse_service import _cycle_time

    result = await _cycle_time(team_id=None, project_id=None)
    assert result.value == "0.0h"


# ── _dependency_health ───────────────────────────────────────


@pytest.mark.asyncio
@patch("services.pulse_service.fetch_all", new_callable=AsyncMock)
@patch("services.pulse_service.fetch_one", new_callable=AsyncMock)
async def test_dependency_health_blocked_blocking(mock_fetch_one, mock_fetch_all):
    """_dependency_health returns blocked and blocking counts."""
    # blocked, blocking, chains
    mock_fetch_one.side_effect = [
        make_record(cnt=4),
        make_record(cnt=2),
        make_record(cnt=6),
    ]
    mock_fetch_all.return_value = [
        make_record(issue_id="TEAM-001", title="Auth module", blocks_count=3),
    ]

    from services.pulse_service import _dependency_health

    result = await _dependency_health(team_id="team1", project_id=None)
    assert result.blocked == 4
    assert result.blocking == 2
    assert result.chains == 6
    assert len(result.bottlenecks) == 1


# ── _burndown ────────────────────────────────────────────────


@pytest.mark.asyncio
@patch("services.pulse_service.fetch_one", new_callable=AsyncMock)
async def test_burndown_14_points(mock_fetch_one):
    """_burndown returns 15 data points (14 days + today)."""
    # Each burndown day makes 2 fetch_one calls (remaining + done)
    mock_fetch_one.return_value = make_record(cnt=7)

    from services.pulse_service import _burndown

    result = await _burndown(team_id=None, project_id=None, days=14)
    assert len(result) == 15  # 14 past days + today
    assert all(p.remaining == 7 for p in result)
    assert all(p.completed == 7 for p in result)


# ── get_pulse (integration) ─────────────────────────────────


@pytest.mark.asyncio
@patch("services.pulse_service._burndown", new_callable=AsyncMock)
@patch("services.pulse_service._cycle_time", new_callable=AsyncMock)
@patch("services.pulse_service._throughput", new_callable=AsyncMock)
@patch("services.pulse_service._velocity", new_callable=AsyncMock)
@patch("services.pulse_service._dependency_health", new_callable=AsyncMock)
@patch("services.pulse_service._team_activity", new_callable=AsyncMock)
@patch("services.pulse_service._status_distribution", new_callable=AsyncMock)
async def test_get_pulse_aggregates_all(
    mock_dist, mock_team, mock_deps, mock_vel, mock_thr, mock_cyc, mock_burn,
):
    """get_pulse calls all sub-metrics and returns PulseResponse."""
    from schemas.pulse import DependencyHealth, MetricValue

    mock_dist.return_value = {"todo": 3, "done": 5}
    mock_team.return_value = []
    mock_deps.return_value = DependencyHealth()
    mock_vel.return_value = MetricValue(value="8", sub="last 7 days")
    mock_thr.return_value = MetricValue(value="2.0", sub="per week")
    mock_cyc.return_value = MetricValue(value="24.0h", sub="avg")
    mock_burn.return_value = []

    from services.pulse_service import get_pulse

    result = await get_pulse(team_id="team1", project_id=1)
    assert result.velocity.value == "8"
    assert result.status_distribution == {"todo": 3, "done": 5}
    mock_dist.assert_called_once_with("team1", 1)
