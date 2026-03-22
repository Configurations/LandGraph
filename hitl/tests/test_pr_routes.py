"""Tests for routes/prs.py — HTTP layer."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient

from core.security import encode_token
from tests.conftest import SAMPLE_USER_ID


NOW = datetime(2026, 3, 22, 12, 0, tzinfo=timezone.utc)

TOKEN = encode_token(str(SAMPLE_USER_ID), "alice@test.com", "member", ["team1"])
AUTH = {"Authorization": f"Bearer {TOKEN}"}


def _pr_response(**overrides) -> dict:
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
    return defaults


# ── GET /api/pm/reviews ──────────────────────────────────────


@pytest.mark.asyncio
@patch("services.pr_service.list_prs", new_callable=AsyncMock)
async def test_list_prs_200(mock_list, app_client: AsyncClient):
    from schemas.pr import PRResponse

    mock_list.return_value = [PRResponse(**_pr_response())]

    resp = await app_client.get("/api/pm/reviews", headers=AUTH)
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["id"] == "PR-ABCD1234"


# ── POST /api/pm/reviews ─────────────────────────────────────


@pytest.mark.asyncio
@patch("services.pr_service.create_pr", new_callable=AsyncMock)
async def test_create_pr_201(mock_create, app_client: AsyncClient):
    from schemas.pr import PRResponse

    mock_create.return_value = PRResponse(**_pr_response())

    resp = await app_client.post(
        "/api/pm/reviews",
        json={"branch": "feat/login", "title": "Add login"},
        headers=AUTH,
    )
    assert resp.status_code == 201
    assert resp.json()["branch"] == "feat/login"


# ── GET /api/pm/reviews/{id} ────────────────────────────────


@pytest.mark.asyncio
@patch("services.pr_service.get_pr", new_callable=AsyncMock)
async def test_get_pr_200(mock_get, app_client: AsyncClient):
    from schemas.pr import PRResponse

    mock_get.return_value = PRResponse(**_pr_response())

    resp = await app_client.get("/api/pm/reviews/PR-ABCD1234", headers=AUTH)
    assert resp.status_code == 200
    assert resp.json()["title"] == "Add login page"


@pytest.mark.asyncio
@patch("services.pr_service.get_pr", new_callable=AsyncMock)
async def test_get_pr_404(mock_get, app_client: AsyncClient):
    mock_get.return_value = None

    resp = await app_client.get("/api/pm/reviews/NOPE", headers=AUTH)
    assert resp.status_code == 404


# ── PUT /api/pm/reviews/{id} ────────────────────────────────


@pytest.mark.asyncio
@patch("services.pr_service.update_status", new_callable=AsyncMock)
async def test_update_pr_200(mock_update, app_client: AsyncClient):
    from schemas.pr import PRResponse

    mock_update.return_value = PRResponse(**_pr_response(status="approved"))

    resp = await app_client.put(
        "/api/pm/reviews/PR-ABCD1234",
        json={"status": "approved", "comment": "LGTM"},
        headers=AUTH,
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "approved"


# ── POST /api/pm/reviews/{id}/merge ─────────────────────────


@pytest.mark.asyncio
@patch("services.pr_service.merge_pr", new_callable=AsyncMock)
async def test_merge_pr_200(mock_merge, app_client: AsyncClient):
    from schemas.pr import PRResponse

    mock_merge.return_value = PRResponse(**_pr_response(status="merged"))

    resp = await app_client.post("/api/pm/reviews/PR-ABCD1234/merge", headers=AUTH)
    assert resp.status_code == 200
    assert resp.json()["status"] == "merged"
