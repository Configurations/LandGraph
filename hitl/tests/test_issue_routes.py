"""Tests for routes/issues.py — HTTP layer."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient

from core.security import encode_token
from tests.conftest import SAMPLE_USER_ID, make_record, set_fetch, set_fetchrow


NOW = datetime(2026, 3, 22, 12, 0, tzinfo=timezone.utc)

TOKEN = encode_token(str(SAMPLE_USER_ID), "alice@test.com", "member", ["team1"])
AUTH = {"Authorization": f"Bearer {TOKEN}"}


def _issue_row(**overrides) -> dict:
    defaults = dict(
        id="TEAM-001", project_id=1, title="Setup CI",
        description="", status="todo", priority=2,
        assignee="alice@test.com", team_id="team1",
        tags=[], phase=None, created_by="bob@test.com",
        created_at=NOW, updated_at=NOW,
        is_blocked=False, blocking_count=0, blocked_by_count=0,
    )
    defaults.update(overrides)
    return make_record(**defaults)


# ── POST /api/pm/issues ──────────────────────────────────────

@pytest.mark.asyncio
@patch("services.issue_service.create_issue", new_callable=AsyncMock)
async def test_create_issue_201(mock_create, app_client: AsyncClient):
    from schemas.issue import IssueResponse

    mock_create.return_value = IssueResponse(**_issue_row())

    resp = await app_client.post(
        "/api/pm/issues?team_id=team1",
        json={"title": "Setup CI"},
        headers=AUTH,
    )
    assert resp.status_code == 201
    assert resp.json()["id"] == "TEAM-001"


# ── GET /api/pm/issues ───────────────────────────────────────

@pytest.mark.asyncio
@patch("services.issue_service.list_issues", new_callable=AsyncMock)
async def test_list_issues_200(mock_list, app_client: AsyncClient):
    from schemas.issue import IssueResponse

    mock_list.return_value = [IssueResponse(**_issue_row())]

    resp = await app_client.get("/api/pm/issues", headers=AUTH)
    assert resp.status_code == 200
    body = resp.json()
    assert isinstance(body, list)
    assert len(body) == 1


# ── GET /api/pm/issues/{id} ──────────────────────────────────

@pytest.mark.asyncio
@patch("services.issue_service.get_issue", new_callable=AsyncMock)
async def test_get_issue_detail(mock_get, app_client: AsyncClient):
    from schemas.issue import IssueDetail

    detail = IssueDetail(**_issue_row(), relations=[], project_name="Proj")
    mock_get.return_value = detail

    resp = await app_client.get("/api/pm/issues/TEAM-001", headers=AUTH)
    assert resp.status_code == 200
    assert resp.json()["title"] == "Setup CI"


@pytest.mark.asyncio
@patch("services.issue_service.get_issue", new_callable=AsyncMock)
async def test_get_issue_404(mock_get, app_client: AsyncClient):
    mock_get.return_value = None

    resp = await app_client.get("/api/pm/issues/NOPE-999", headers=AUTH)
    assert resp.status_code == 404


# ── PUT /api/pm/issues/{id} ──────────────────────────────────

@pytest.mark.asyncio
@patch("services.issue_service.update_issue", new_callable=AsyncMock)
async def test_update_issue_200(mock_update, app_client: AsyncClient):
    from schemas.issue import IssueResponse

    mock_update.return_value = IssueResponse(**_issue_row(status="in-progress"))

    resp = await app_client.put(
        "/api/pm/issues/TEAM-001",
        json={"status": "in-progress"},
        headers=AUTH,
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "in-progress"


# ── DELETE /api/pm/issues/{id} ────────────────────────────────

@pytest.mark.asyncio
@patch("services.issue_service.delete_issue", new_callable=AsyncMock)
async def test_delete_issue_204(mock_del, app_client: AsyncClient):
    mock_del.return_value = True

    resp = await app_client.delete("/api/pm/issues/TEAM-001", headers=AUTH)
    assert resp.status_code == 204


@pytest.mark.asyncio
@patch("services.issue_service.delete_issue", new_callable=AsyncMock)
async def test_delete_issue_404(mock_del, app_client: AsyncClient):
    mock_del.return_value = False

    resp = await app_client.delete("/api/pm/issues/NOPE-999", headers=AUTH)
    assert resp.status_code == 404


# ── GET /api/pm/issues/search ─────────────────────────────────

@pytest.mark.asyncio
@patch("services.issue_service.search_issues", new_callable=AsyncMock)
async def test_search_issues_200(mock_search, app_client: AsyncClient):
    from schemas.issue import IssueResponse

    mock_search.return_value = [IssueResponse(**_issue_row())]

    resp = await app_client.get(
        "/api/pm/issues/search?q=CI&team_id=team1",
        headers=AUTH,
    )
    assert resp.status_code == 200
    assert len(resp.json()) == 1
