"""Tests for services/project_service.py."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tests.conftest import SAMPLE_USER_ID, FakeRecord, make_record


# ── Helpers ──────────────────────────────────────────────────

def _project_row(**overrides):
    """Build a fake project DB row."""
    defaults = dict(
        id=1, name="My Project", slug="my-project", team_id="team1",
        language="fr", git_service="github", git_url="https://github.com",
        git_login="user", git_repo_name="user/repo",
        status="on-track", color="#6366f1",
        created_at=datetime(2026, 3, 20, tzinfo=timezone.utc),
        updated_at=datetime(2026, 3, 20, tzinfo=timezone.utc),
    )
    defaults.update(overrides)
    return make_record(**defaults)


# ── create_project ───────────────────────────────────────────

@pytest.mark.asyncio
async def test_create_project_success():
    """create_project creates dirs, writes .project, inserts DB row."""
    from schemas.project import ProjectCreate

    data = ProjectCreate(name="Test", slug="test", team_id="team1")
    row = _project_row(slug="test", name="Test")

    with (
        patch("services.project_service.os.makedirs") as mk,
        patch("builtins.open", MagicMock()),
        patch("services.project_service.fetch_one", new_callable=AsyncMock, return_value=row),
    ):
        from services.project_service import create_project
        result = await create_project(data)

    assert result.slug == "test"
    assert result.name == "Test"
    assert mk.call_count == 3  # repo, docs, uploads


@pytest.mark.asyncio
async def test_create_project_slug_collision():
    """create_project raises RuntimeError when DB returns None."""
    from schemas.project import ProjectCreate

    data = ProjectCreate(name="Dup", slug="dup", team_id="team1")

    with (
        patch("services.project_service.os.makedirs"),
        patch("builtins.open", MagicMock()),
        patch("services.project_service.fetch_one", new_callable=AsyncMock, return_value=None),
    ):
        from services.project_service import create_project
        with pytest.raises(RuntimeError, match="insert_failed"):
            await create_project(data)


# ── check_slug_exists ────────────────────────────────────────

@pytest.mark.asyncio
async def test_check_slug_exists_true():
    """check_slug_exists returns exists=True when dir exists."""
    with patch("services.project_service.os.path.isdir", return_value=True):
        from services.project_service import check_slug_exists
        result = await check_slug_exists("my-proj")
    assert result.exists is True


@pytest.mark.asyncio
async def test_check_slug_exists_false():
    """check_slug_exists returns exists=False when dir missing."""
    with patch("services.project_service.os.path.isdir", return_value=False):
        from services.project_service import check_slug_exists
        result = await check_slug_exists("nope")
    assert result.exists is False


# ── list_projects ────────────────────────────────────────────

@pytest.mark.asyncio
async def test_list_projects_admin_sees_all():
    """Admin with no team filter sees all projects."""
    rows = [_project_row(id=1, slug="a"), _project_row(id=2, slug="b")]

    with patch("services.project_service.fetch_all", new_callable=AsyncMock, return_value=rows):
        from services.project_service import list_projects
        result = await list_projects(team_id=None, user_teams=[], role="admin")

    assert len(result) == 2


@pytest.mark.asyncio
async def test_list_projects_member_sees_own_teams():
    """Member sees only their team's projects."""
    rows = [_project_row(id=1, slug="mine")]

    with patch("services.project_service.fetch_all", new_callable=AsyncMock, return_value=rows):
        from services.project_service import list_projects
        result = await list_projects(team_id=None, user_teams=["team1"], role="member")

    assert len(result) == 1
    assert result[0].slug == "mine"


@pytest.mark.asyncio
async def test_list_projects_member_no_teams():
    """Member with no teams gets empty list."""
    from services.project_service import list_projects
    result = await list_projects(team_id=None, user_teams=[], role="member")
    assert result == []


# ── get_project ──────────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_project_found():
    """get_project returns project when row exists."""
    row = _project_row(slug="found")
    with patch("services.project_service.fetch_one", new_callable=AsyncMock, return_value=row):
        from services.project_service import get_project
        result = await get_project("found")
    assert result is not None
    assert result.slug == "found"


@pytest.mark.asyncio
async def test_get_project_not_found():
    """get_project returns None when row missing."""
    with patch("services.project_service.fetch_one", new_callable=AsyncMock, return_value=None):
        from services.project_service import get_project
        result = await get_project("ghost")
    assert result is None
