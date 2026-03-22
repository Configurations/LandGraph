"""Tests for routes/project_types.py — project type HTTP layer."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient

from core.security import encode_token
from tests.conftest import SAMPLE_USER_ID


TOKEN = encode_token(str(SAMPLE_USER_ID), "alice@test.com", "member", ["team1"])
AUTH = {"Authorization": f"Bearer {TOKEN}"}


def _pt_response(**overrides):
    from schemas.project_type import ProjectTypeResponse, WorkflowTemplate
    defaults = dict(
        id="saas-starter",
        name="SaaS Starter",
        description="Standard SaaS template",
        team="team1",
        workflows=[
            WorkflowTemplate(name="Discovery", filename="discovery.wrk.json"),
        ],
    )
    defaults.update(overrides)
    return ProjectTypeResponse(**defaults)


# ── GET /api/project-types ───────────────────────────────────


@pytest.mark.asyncio
@patch("routes.project_types.project_type_service.list_project_types", new_callable=AsyncMock)
async def test_list_project_types_200(mock_list, app_client: AsyncClient):
    """GET /api/project-types returns 200 with a list."""
    mock_list.return_value = [_pt_response()]

    resp = await app_client.get("/api/project-types", headers=AUTH)
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["id"] == "saas-starter"


# ── GET /api/project-types/{id} ─────────────────────────────


@pytest.mark.asyncio
@patch("routes.project_types.project_type_service.get_project_type", new_callable=AsyncMock)
async def test_get_project_type_200(mock_get, app_client: AsyncClient):
    """GET /api/project-types/{id} returns 200."""
    mock_get.return_value = _pt_response()

    resp = await app_client.get("/api/project-types/saas-starter", headers=AUTH)
    assert resp.status_code == 200
    assert resp.json()["name"] == "SaaS Starter"


@pytest.mark.asyncio
@patch("routes.project_types.project_type_service.get_project_type", new_callable=AsyncMock)
async def test_get_project_type_404(mock_get, app_client: AsyncClient):
    """GET /api/project-types/{id} returns 404 when not found."""
    mock_get.return_value = None

    resp = await app_client.get("/api/project-types/nonexistent", headers=AUTH)
    assert resp.status_code == 404


# ── POST /api/projects/{slug}/apply-type/{id} ───────────────


@pytest.mark.asyncio
@patch("routes.project_types.project_type_service.apply_project_type", new_callable=AsyncMock)
async def test_apply_project_type_200(mock_apply, app_client: AsyncClient):
    """POST apply-type returns 200 with workflow_ids."""
    mock_apply.return_value = [1, 2, 3]

    resp = await app_client.post(
        "/api/projects/tracker/apply-type/saas-starter",
        headers=AUTH,
        json={},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    assert data["workflow_ids"] == [1, 2, 3]


@pytest.mark.asyncio
@patch("routes.project_types.project_type_service.apply_project_type", new_callable=AsyncMock)
async def test_apply_project_type_404_when_empty(mock_apply, app_client: AsyncClient):
    """POST apply-type returns 404 when project type not found."""
    mock_apply.return_value = []

    resp = await app_client.post(
        "/api/projects/tracker/apply-type/nonexistent",
        headers=AUTH,
        json={},
    )
    assert resp.status_code == 404
