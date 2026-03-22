"""Tests for routes/workflow.py — HTTP layer."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient

from core.security import encode_token
from tests.conftest import SAMPLE_USER_ID


TOKEN = encode_token(str(SAMPLE_USER_ID), "alice@test.com", "member", ["team1"])
AUTH = {"Authorization": f"Bearer {TOKEN}"}


# ── GET /api/projects/{slug}/workflow ────────────────────────


@pytest.mark.asyncio
@patch("routes.workflow.workflow_service.get_workflow_status", new_callable=AsyncMock)
@patch("routes.workflow._get_project_team", new_callable=AsyncMock)
async def test_get_workflow_200(mock_team, mock_wf, app_client: AsyncClient):
    """GET /api/projects/{slug}/workflow returns 200 with phases."""
    from schemas.workflow import PhaseStatus, WorkflowStatusResponse

    mock_team.return_value = "team1"
    mock_wf.return_value = WorkflowStatusResponse(
        phases=[PhaseStatus(id="discovery", name="Discovery", status="completed")],
        current_phase=None,
        total_phases=1,
        completed_phases=1,
    )

    resp = await app_client.get("/api/projects/tracker/workflow", headers=AUTH)
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["phases"]) == 1
    assert data["phases"][0]["id"] == "discovery"
    assert data["total_phases"] == 1


# ── GET /api/projects/{slug}/workflow/{phase_id} ─────────────


@pytest.mark.asyncio
@patch("routes.workflow.workflow_service.get_phase_detail", new_callable=AsyncMock)
@patch("routes.workflow._get_project_team", new_callable=AsyncMock)
async def test_get_phase_detail_200(mock_team, mock_detail, app_client: AsyncClient):
    """GET /api/projects/{slug}/workflow/{phase} returns 200."""
    from schemas.workflow import PhaseAgent, PhaseStatus

    mock_team.return_value = "team1"
    mock_detail.return_value = PhaseStatus(
        id="discovery",
        name="Discovery",
        status="active",
        agents=[PhaseAgent(agent_id="analyst", name="Analyst", status="active")],
    )

    resp = await app_client.get(
        "/api/projects/tracker/workflow/discovery", headers=AUTH,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == "discovery"
    assert len(data["agents"]) == 1


@pytest.mark.asyncio
@patch("routes.workflow.workflow_service.get_phase_detail", new_callable=AsyncMock)
@patch("routes.workflow._get_project_team", new_callable=AsyncMock)
async def test_get_phase_detail_404(mock_team, mock_detail, app_client: AsyncClient):
    """GET /api/projects/{slug}/workflow/{phase} returns 404 when not found."""
    mock_team.return_value = "team1"
    mock_detail.return_value = None

    resp = await app_client.get(
        "/api/projects/tracker/workflow/nonexistent", headers=AUTH,
    )
    assert resp.status_code == 404
