"""Tests for routes/workflows.py — multi-workflow HTTP layer."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient

from core.security import encode_token
from tests.conftest import SAMPLE_USER_ID


TOKEN = encode_token(str(SAMPLE_USER_ID), "alice@test.com", "member", ["team1"])
AUTH = {"Authorization": f"Bearer {TOKEN}"}


def _wf_response(**overrides):
    """Build a ProjectWorkflowResponse for mock returns."""
    from schemas.workflow import ProjectWorkflowResponse
    defaults = dict(
        id=1,
        project_slug="tracker",
        workflow_name="Discovery",
        workflow_type="discovery",
        workflow_json_path="/path/discovery.wrk.json",
        status="pending",
        mode="sequential",
        priority=90,
        iteration=1,
    )
    defaults.update(overrides)
    return ProjectWorkflowResponse(**defaults)


# ── GET /api/projects/{slug}/workflows ───────────────────────


@pytest.mark.asyncio
@patch("routes.workflows.multi_workflow_service.list_workflows", new_callable=AsyncMock)
async def test_list_workflows_200(mock_list, app_client: AsyncClient):
    """GET /api/projects/{slug}/workflows returns 200 with a list."""
    mock_list.return_value = [_wf_response(id=1), _wf_response(id=2)]

    resp = await app_client.get("/api/projects/tracker/workflows", headers=AUTH)
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 2
    assert data[0]["workflow_name"] == "Discovery"


# ── POST /api/projects/{slug}/workflows ──────────────────────


@pytest.mark.asyncio
@patch("routes.workflows.multi_workflow_service.create_workflow", new_callable=AsyncMock)
async def test_create_workflow_201(mock_create, app_client: AsyncClient):
    """POST /api/projects/{slug}/workflows returns 201."""
    mock_create.return_value = _wf_response(id=42)

    resp = await app_client.post(
        "/api/projects/tracker/workflows",
        headers=AUTH,
        json={
            "workflow_name": "Discovery",
            "workflow_type": "discovery",
            "workflow_json_path": "/path/discovery.wrk.json",
        },
    )
    assert resp.status_code == 201
    assert resp.json()["id"] == 42


# ── GET /api/projects/{slug}/workflows/{id} ──────────────────


@pytest.mark.asyncio
@patch("routes.workflows.multi_workflow_service.get_workflow", new_callable=AsyncMock)
async def test_get_workflow_200(mock_get, app_client: AsyncClient):
    """GET /api/projects/{slug}/workflows/{id} returns 200."""
    mock_get.return_value = _wf_response(id=1, project_slug="tracker")

    resp = await app_client.get("/api/projects/tracker/workflows/1", headers=AUTH)
    assert resp.status_code == 200
    assert resp.json()["id"] == 1


@pytest.mark.asyncio
@patch("routes.workflows.multi_workflow_service.get_workflow", new_callable=AsyncMock)
async def test_get_workflow_404(mock_get, app_client: AsyncClient):
    """GET /api/projects/{slug}/workflows/{id} returns 404 when missing."""
    mock_get.return_value = None

    resp = await app_client.get("/api/projects/tracker/workflows/999", headers=AUTH)
    assert resp.status_code == 404


# ── POST activate/pause/complete/relaunch ────────────────────


@pytest.mark.asyncio
@patch("routes.workflows.multi_workflow_service.activate_workflow", new_callable=AsyncMock)
async def test_activate_workflow_200(mock_act, app_client: AsyncClient):
    """POST activate returns 200 on valid transition."""
    mock_act.return_value = _wf_response(status="active")

    resp = await app_client.post(
        "/api/projects/tracker/workflows/1/activate", headers=AUTH,
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "active"


@pytest.mark.asyncio
@patch("routes.workflows.multi_workflow_service.pause_workflow", new_callable=AsyncMock)
async def test_pause_workflow_200(mock_pause, app_client: AsyncClient):
    """POST pause returns 200 on valid transition."""
    mock_pause.return_value = _wf_response(status="paused")

    resp = await app_client.post(
        "/api/projects/tracker/workflows/1/pause", headers=AUTH,
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "paused"


@pytest.mark.asyncio
@patch("routes.workflows.multi_workflow_service.complete_workflow", new_callable=AsyncMock)
async def test_complete_workflow_200(mock_complete, app_client: AsyncClient):
    """POST complete returns 200 on valid transition."""
    mock_complete.return_value = _wf_response(status="completed")

    resp = await app_client.post(
        "/api/projects/tracker/workflows/1/complete", headers=AUTH,
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "completed"


@pytest.mark.asyncio
@patch("routes.workflows.multi_workflow_service.relaunch_workflow", new_callable=AsyncMock)
async def test_relaunch_workflow_200(mock_relaunch, app_client: AsyncClient):
    """POST relaunch returns 200 with a new iteration."""
    mock_relaunch.return_value = _wf_response(id=3, iteration=2, status="pending")

    resp = await app_client.post(
        "/api/projects/tracker/workflows/1/relaunch", headers=AUTH,
    )
    assert resp.status_code == 200
    assert resp.json()["iteration"] == 2
