"""Tests for routes/auth.py + services/auth_service.py."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from httpx import AsyncClient

from core.security import encode_token, hash_password
from tests.conftest import SAMPLE_USER_ID, FakeRecord, make_record, set_fetch, set_fetchrow


# ── POST /api/auth/login ───────────────────────────────────────

@pytest.mark.asyncio
async def test_login_success(app_client: AsyncClient, mock_pool: AsyncMock):
    hashed = hash_password("secret123")
    user_row = make_record(
        id=SAMPLE_USER_ID, email="alice@test.com", password_hash=hashed,
        display_name="Alice", role="member", is_active=True,
        auth_type="local", culture="fr",
    )
    # First call: user lookup; second call: update last_login
    mock_pool.fetchrow.side_effect = [user_row, None]
    mock_pool.fetch.return_value = [make_record(team_id="team1")]

    resp = await app_client.post("/api/auth/login", json={
        "email": "alice@test.com", "password": "secret123",
    })
    assert resp.status_code == 200
    body = resp.json()
    assert "token" in body
    assert body["user"]["email"] == "alice@test.com"


@pytest.mark.asyncio
async def test_login_wrong_password(app_client: AsyncClient, mock_pool: AsyncMock):
    hashed = hash_password("correct")
    user_row = make_record(
        id=SAMPLE_USER_ID, email="alice@test.com", password_hash=hashed,
        display_name="Alice", role="member", is_active=True,
        auth_type="local", culture="fr",
    )
    set_fetchrow(mock_pool, user_row)

    resp = await app_client.post("/api/auth/login", json={
        "email": "alice@test.com", "password": "wrong",
    })
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_login_undefined_role(app_client: AsyncClient, mock_pool: AsyncMock):
    hashed = hash_password("pass")
    user_row = make_record(
        id=SAMPLE_USER_ID, email="bob@test.com", password_hash=hashed,
        display_name="Bob", role="undefined", is_active=True,
        auth_type="local", culture="fr",
    )
    set_fetchrow(mock_pool, user_row)

    resp = await app_client.post("/api/auth/login", json={
        "email": "bob@test.com", "password": "pass",
    })
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_login_disabled_account(app_client: AsyncClient, mock_pool: AsyncMock):
    hashed = hash_password("pass")
    user_row = make_record(
        id=SAMPLE_USER_ID, email="dis@test.com", password_hash=hashed,
        display_name="Dis", role="member", is_active=False,
        auth_type="local", culture="fr",
    )
    set_fetchrow(mock_pool, user_row)

    resp = await app_client.post("/api/auth/login", json={
        "email": "dis@test.com", "password": "pass",
    })
    assert resp.status_code == 403


# ── POST /api/auth/register ────────────────────────────────────

@pytest.mark.asyncio
async def test_register_success(app_client: AsyncClient, mock_pool: AsyncMock):
    mock_pool.fetchrow.return_value = None  # no existing user
    mock_pool.execute.return_value = "INSERT 1"

    with patch("services.auth_service.send_reset_email", new_callable=AsyncMock, return_value=True):
        resp = await app_client.post("/api/auth/register", json={
            "email": "new@test.com", "culture": "fr",
        })
    assert resp.status_code == 200
    assert resp.json()["ok"] is True


@pytest.mark.asyncio
async def test_register_email_exists(app_client: AsyncClient, mock_pool: AsyncMock):
    set_fetchrow(mock_pool, make_record(id=SAMPLE_USER_ID))

    resp = await app_client.post("/api/auth/register", json={
        "email": "dup@test.com",
    })
    assert resp.status_code == 409


# ── GET /api/auth/me ───────────────────────────────────────────

@pytest.mark.asyncio
async def test_me_success(app_client: AsyncClient, mock_pool: AsyncMock):
    token = encode_token(str(SAMPLE_USER_ID), "a@b.com", "member", ["t1"])
    user_row = make_record(
        id=SAMPLE_USER_ID, email="a@b.com", display_name="A",
        role="member", auth_type="local", culture="fr",
    )
    mock_pool.fetchrow.return_value = user_row
    mock_pool.fetch.return_value = [make_record(team_id="t1")]

    resp = await app_client.get("/api/auth/me", headers={
        "Authorization": f"Bearer {token}",
    })
    assert resp.status_code == 200
    assert resp.json()["email"] == "a@b.com"


@pytest.mark.asyncio
async def test_me_invalid_jwt(app_client: AsyncClient):
    resp = await app_client.get("/api/auth/me", headers={
        "Authorization": "Bearer garbage",
    })
    assert resp.status_code == 401


# ── POST /api/auth/reset-password ──────────────────────────────

@pytest.mark.asyncio
async def test_reset_password_success(app_client: AsyncClient, mock_pool: AsyncMock):
    old_hash = hash_password("oldpass")
    row = make_record(id=SAMPLE_USER_ID, password_hash=old_hash)
    set_fetchrow(mock_pool, row)

    resp = await app_client.post("/api/auth/reset-password", json={
        "email": "a@b.com", "old_password": "oldpass", "new_password": "newpass123",
    })
    assert resp.status_code == 200
    assert resp.json()["ok"] is True


@pytest.mark.asyncio
async def test_reset_password_wrong_old(app_client: AsyncClient, mock_pool: AsyncMock):
    old_hash = hash_password("correct")
    row = make_record(id=SAMPLE_USER_ID, password_hash=old_hash)
    set_fetchrow(mock_pool, row)

    resp = await app_client.post("/api/auth/reset-password", json={
        "email": "a@b.com", "old_password": "wrong", "new_password": "new123456",
    })
    assert resp.status_code == 401


# ── GET /api/auth/google/client-id ─────────────────────────────

@pytest.mark.asyncio
async def test_google_client_id_enabled(app_client: AsyncClient):
    cfg = {"google_oauth": {"enabled": True, "client_id": "test-id-123"}}
    with patch("routes.auth.load_json_config", return_value=cfg):
        resp = await app_client.get("/api/auth/google/client-id")
    assert resp.status_code == 200
    assert resp.json()["client_id"] == "test-id-123"


@pytest.mark.asyncio
async def test_google_client_id_disabled(app_client: AsyncClient):
    with patch("routes.auth.load_json_config", return_value={}):
        resp = await app_client.get("/api/auth/google/client-id")
    assert resp.status_code == 200
    assert resp.json()["client_id"] is None
