"""Tests for routes/pulse.py — HTTP layer."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient

from core.security import encode_token
from tests.conftest import SAMPLE_USER_ID


TOKEN = encode_token(str(SAMPLE_USER_ID), "alice@test.com", "member", ["team1"])
AUTH = {"Authorization": f"Bearer {TOKEN}"}


# ── GET /api/pm/pulse ────────────────────────────────────────


@pytest.mark.asyncio
@patch("services.pulse_service.get_pulse", new_callable=AsyncMock)
async def test_get_pulse_200(mock_get_pulse, app_client: AsyncClient):
    """GET /api/pm/pulse returns 200 with full pulse data."""
    from schemas.pulse import (
        DependencyHealth,
        MetricValue,
        PulseResponse,
    )

    mock_get_pulse.return_value = PulseResponse(
        status_distribution={"todo": 5, "done": 3},
        team_activity=[],
        dependency_health=DependencyHealth(blocked=1, blocking=2),
        velocity=MetricValue(value="8", sub="last 7 days"),
        throughput=MetricValue(value="2.0", sub="per week"),
        cycle_time=MetricValue(value="24.0h", sub="avg"),
        burndown=[],
    )

    resp = await app_client.get("/api/pm/pulse", headers=AUTH)
    assert resp.status_code == 200
    data = resp.json()
    assert data["status_distribution"]["todo"] == 5
    assert data["velocity"]["value"] == "8"
    assert data["dependency_health"]["blocked"] == 1


@pytest.mark.asyncio
@patch("services.pulse_service.get_pulse", new_callable=AsyncMock)
async def test_get_pulse_with_filters(mock_get_pulse, app_client: AsyncClient):
    """GET /api/pm/pulse forwards team_id and project_id params."""
    from schemas.pulse import DependencyHealth, MetricValue, PulseResponse

    mock_get_pulse.return_value = PulseResponse(
        velocity=MetricValue(value="0", sub=""),
        throughput=MetricValue(value="0", sub=""),
        cycle_time=MetricValue(value="0h", sub=""),
    )

    resp = await app_client.get(
        "/api/pm/pulse?team_id=team1&project_id=42", headers=AUTH,
    )
    assert resp.status_code == 200
    mock_get_pulse.assert_called_once_with(team_id="team1", project_id=42)
