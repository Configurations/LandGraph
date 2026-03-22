"""Tests for routes/teams.py + services/team_service.py."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient

from core.security import encode_token
from tests.conftest import SAMPLE_USER_ID, make_record, set_fetch, set_fetchrow


ADMIN_TOKEN = encode_token(str(SAMPLE_USER_ID), "admin@t.com", "admin", ["team1"])
MEMBER_TOKEN = encode_token(str(SAMPLE_USER_ID), "m@t.com", "member", ["team1"])
OTHER_TOKEN = encode_token(str(SAMPLE_USER_ID), "o@t.com", "member", ["team2"])

TEAMS_CONFIG = [
    {"id": "team1", "name": "Team 1", "directory": "Team1"},
    {"id": "team2", "name": "Team 2", "directory": "Team2"},
]


# ── GET /api/teams ─────────────────────────────────────────────

@pytest.mark.asyncio
async def test_list_teams_member(app_client: AsyncClient, mock_pool: AsyncMock):
    mock_pool.fetch.return_value = [make_record(team_id="team1")]
    mock_pool.fetchrow.return_value = make_record(cnt=3)

    with patch("services.team_service.load_teams", return_value=TEAMS_CONFIG):
        resp = await app_client.get("/api/teams", headers={
            "Authorization": f"Bearer {MEMBER_TOKEN}",
        })

    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["id"] == "team1"


@pytest.mark.asyncio
async def test_list_teams_admin_sees_all(app_client: AsyncClient, mock_pool: AsyncMock):
    mock_pool.fetchrow.return_value = make_record(cnt=2)

    with patch("services.team_service.load_teams", return_value=TEAMS_CONFIG):
        resp = await app_client.get("/api/teams", headers={
            "Authorization": f"Bearer {ADMIN_TOKEN}",
        })

    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 2


# ── GET /api/teams/{id}/members ────────────────────────────────

@pytest.mark.asyncio
async def test_list_members_success(app_client: AsyncClient, mock_pool: AsyncMock):
    mock_pool.fetch.return_value = [
        make_record(
            id=SAMPLE_USER_ID, email="a@t.com", display_name="A",
            role_global="member", role_team="member",
            is_active=True, last_login=None,
        ),
    ]

    resp = await app_client.get("/api/teams/team1/members", headers={
        "Authorization": f"Bearer {MEMBER_TOKEN}",
    })
    assert resp.status_code == 200
    assert len(resp.json()) == 1
    assert resp.json()[0]["email"] == "a@t.com"


@pytest.mark.asyncio
async def test_list_members_forbidden(app_client: AsyncClient):
    resp = await app_client.get("/api/teams/team1/members", headers={
        "Authorization": f"Bearer {OTHER_TOKEN}",
    })
    assert resp.status_code == 403


# ── POST /api/teams/{id}/members ───────────────────────────────

@pytest.mark.asyncio
async def test_invite_member_admin(app_client: AsyncClient, mock_pool: AsyncMock):
    # User lookup returns existing user
    uid = uuid.uuid4()
    mock_pool.fetchrow.side_effect = [
        make_record(id=uid),  # existing user
        None,                 # not already a member
    ]
    mock_pool.execute.return_value = "INSERT 1"

    resp = await app_client.post("/api/teams/team1/members", json={
        "email": "new@test.com", "display_name": "New", "role": "member",
    }, headers={"Authorization": f"Bearer {ADMIN_TOKEN}"})

    assert resp.status_code == 200
    assert resp.json()["ok"] is True


@pytest.mark.asyncio
async def test_invite_member_forbidden_non_admin(app_client: AsyncClient):
    resp = await app_client.post("/api/teams/team1/members", json={
        "email": "x@t.com",
    }, headers={"Authorization": f"Bearer {MEMBER_TOKEN}"})

    assert resp.status_code == 403
