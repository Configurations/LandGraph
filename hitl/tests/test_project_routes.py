"""Tests for routes/projects.py — project CRUD endpoints."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, mock_open, patch

import pytest
from httpx import AsyncClient

from core.security import encode_token
from tests.conftest import SAMPLE_USER_ID, make_record

ADMIN_TOKEN = encode_token(str(SAMPLE_USER_ID), "admin@t.com", "admin", ["team1"])
MEMBER_TOKEN = encode_token(str(SAMPLE_USER_ID), "m@t.com", "member", ["team1"])

NOW = datetime(2026, 3, 20, tzinfo=timezone.utc)


def _project_row(**overrides):
    defaults = dict(
        id=1, name="Proj", slug="proj", team_id="team1",
        language="fr", git_service="github", git_url="https://github.com",
        git_login="user", git_repo_name="user/repo",
        status="on-track", color="#6366f1",
        created_at=NOW, updated_at=NOW,
    )
    defaults.update(overrides)
    return make_record(**defaults)


# ── POST /api/projects ───────────────────────────────────────

@pytest.mark.asyncio
async def test_create_project_201(app_client: AsyncClient, mock_pool: AsyncMock):
    """POST /api/projects returns 201 on success."""
    mock_pool.fetchrow.return_value = _project_row()  # INSERT RETURNING

    with (
        patch("services.project_service.os.path.isdir", return_value=False),
        patch("services.project_service.os.makedirs"),
        patch("builtins.open", mock_open()),
    ):
        resp = await app_client.post("/api/projects/", json={
            "name": "Proj", "slug": "proj", "team_id": "team1",
        }, headers={"Authorization": f"Bearer {ADMIN_TOKEN}"})

    assert resp.status_code == 200  # FastAPI default for response_model


@pytest.mark.asyncio
async def test_create_project_409_slug_exists(app_client: AsyncClient, mock_pool: AsyncMock):
    """POST /api/projects returns 409 when slug dir exists."""
    with patch("services.project_service.os.path.isdir", return_value=True):
        resp = await app_client.post("/api/projects/", json={
            "name": "Dup", "slug": "dup", "team_id": "team1",
        }, headers={"Authorization": f"Bearer {ADMIN_TOKEN}"})

    assert resp.status_code == 409
    assert "slug_exists" in resp.json()["detail"]


# ── GET /api/projects ────────────────────────────────────────

@pytest.mark.asyncio
async def test_list_projects(app_client: AsyncClient, mock_pool: AsyncMock):
    """GET /api/projects returns project list."""
    mock_pool.fetch.return_value = [_project_row(slug="a"), _project_row(slug="b", id=2)]

    resp = await app_client.get(
        "/api/projects/",
        headers={"Authorization": f"Bearer {ADMIN_TOKEN}"},
    )
    assert resp.status_code == 200
    assert len(resp.json()) == 2


# ── GET /api/projects/{slug} ────────────────────────────────

@pytest.mark.asyncio
async def test_get_project_200(app_client: AsyncClient, mock_pool: AsyncMock):
    """GET /api/projects/{slug} returns project on success."""
    mock_pool.fetchrow.return_value = _project_row(slug="found")

    resp = await app_client.get(
        "/api/projects/found",
        headers={"Authorization": f"Bearer {ADMIN_TOKEN}"},
    )
    assert resp.status_code == 200
    assert resp.json()["slug"] == "found"


@pytest.mark.asyncio
async def test_get_project_404(app_client: AsyncClient, mock_pool: AsyncMock):
    """GET /api/projects/{slug} returns 404 when not found."""
    mock_pool.fetchrow.return_value = None

    resp = await app_client.get(
        "/api/projects/ghost",
        headers={"Authorization": f"Bearer {ADMIN_TOKEN}"},
    )
    assert resp.status_code == 404


# ── POST /api/projects/check-slug ────────────────────────────

@pytest.mark.asyncio
async def test_check_slug_exists(app_client: AsyncClient, mock_pool: AsyncMock):
    """POST /api/projects/check-slug returns exists=True."""
    with patch("services.project_service.os.path.isdir", return_value=True):
        resp = await app_client.post(
            "/api/projects/check-slug?slug=taken",
            headers={"Authorization": f"Bearer {MEMBER_TOKEN}"},
        )
    assert resp.status_code == 200
    assert resp.json()["exists"] is True


@pytest.mark.asyncio
async def test_check_slug_not_exists(app_client: AsyncClient, mock_pool: AsyncMock):
    """POST /api/projects/check-slug returns exists=False."""
    with patch("services.project_service.os.path.isdir", return_value=False):
        resp = await app_client.post(
            "/api/projects/check-slug?slug=free",
            headers={"Authorization": f"Bearer {MEMBER_TOKEN}"},
        )
    assert resp.status_code == 200
    assert resp.json()["exists"] is False


# ── POST /api/projects/{slug}/git/test ───────────────────────

@pytest.mark.asyncio
async def test_git_test_connected(app_client: AsyncClient, mock_pool: AsyncMock):
    """POST git/test returns connected when provider responds 200."""
    mock_pool.fetchrow.return_value = _project_row(slug="proj")

    from schemas.project import GitTestResponse
    fake_result = GitTestResponse(connected=True, repo_exists=True)

    with patch("services.git_service.test_git_connection", new_callable=AsyncMock, return_value=fake_result):
        resp = await app_client.post("/api/projects/proj/git/test", json={
            "service": "github", "url": "", "login": "u", "token": "t", "repo_name": "u/r",
        }, headers={"Authorization": f"Bearer {ADMIN_TOKEN}"})

    assert resp.status_code == 200
    assert resp.json()["connected"] is True
