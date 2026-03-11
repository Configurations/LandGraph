"""Fixtures pour les tests de la console HITL (hitl/server.py)."""
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest


# ── Mock DB rows ─────────────────────────────────

def _make_user_row(
    uid=1, email="user@test.com", password_hash="$2b$12$hash", display_name="User",
    role="member", is_active=True, auth_type="local", culture="fr", last_login=None,
):
    """Simule une row SELECT de hitl_users."""
    return (uid, email, password_hash, display_name, role, is_active, auth_type)


def _make_question_row(
    qid=1, thread_id="t-1", agent_id="lead_dev", team_id="team1",
    request_type="approval", prompt="Valider le PRD ?",
    context=None, channel="discord", status="pending",
    response=None, reviewer=None, response_channel=None,
    created_at=None, answered_at=None, expires_at=None,
    reminded_at=None, remind_count=0,
):
    created_at = created_at or datetime(2025, 1, 15, 10, 0, tzinfo=timezone.utc)
    return (
        qid, thread_id, agent_id, team_id, request_type, prompt,
        context or {}, channel, status, response, reviewer,
        response_channel, created_at, answered_at, expires_at,
        reminded_at, remind_count,
    )


class FakeCursor:
    """Curseur PostgreSQL factice pour les tests."""

    def __init__(self, results=None):
        self._results = list(results or [])
        self._idx = 0
        self.rowcount = 0
        self._last_query = None
        self._last_params = None

    def execute(self, query, params=None):
        self._last_query = query
        self._last_params = params
        self.rowcount = 1

    def fetchone(self):
        if self._idx < len(self._results):
            row = self._results[self._idx]
            self._idx += 1
            return row
        return None

    def fetchall(self):
        rows = self._results[self._idx:]
        self._idx = len(self._results)
        return rows

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass


class FakeConn:
    """Connexion PostgreSQL factice."""

    def __init__(self, cursor=None):
        self._cursor = cursor or FakeCursor()

    def cursor(self):
        return self._cursor

    def close(self):
        pass


@pytest.fixture
def mock_conn():
    """Retourne un FakeConn par defaut (pas de resultats)."""
    return FakeConn()


@pytest.fixture
def hitl_app(tmp_path):
    """Import hitl.server avec les deps mockees, retourne le module."""
    # Creer un config minimal
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    teams_dir = config_dir / "Teams"
    teams_dir.mkdir()
    (teams_dir / "teams.json").write_text(json.dumps({
        "teams": [{"id": "team1", "name": "Team 1", "directory": "Team1"}],
    }))
    (config_dir / "hitl.json").write_text(json.dumps({
        "auth": {"jwt_expire_hours": 24, "allow_registration": True},
        "google_oauth": {"enabled": True, "client_id": "test-client-id", "allowed_domains": ["test.com"]},
    }))

    # Patch l'env
    env_patches = {
        "DATABASE_URI": "postgresql://test:test@localhost/test",
        "HITL_JWT_SECRET": "test-jwt-secret-for-unit-tests",
    }

    hitl_path = str(Path(__file__).resolve().parent.parent.parent / "hitl")
    if hitl_path not in sys.path:
        sys.path.insert(0, hitl_path)

    # Remove cached module
    for key in list(sys.modules.keys()):
        if "hitl" in key and "test" not in key:
            pass  # don't remove test modules

    # We need to patch psycopg.connect before importing
    mock_psycopg = MagicMock()
    with patch.dict(os.environ, env_patches):
        with patch.dict(sys.modules, {"psycopg": mock_psycopg}):
            # Force re-read of config
            if "server" in sys.modules:
                del sys.modules["server"]

            # Patch the config loading
            old_cwd = os.getcwd()
            os.chdir(tmp_path)
            try:
                import server as hitl_server
            finally:
                os.chdir(old_cwd)

    # Override JWT_SECRET for deterministic tests
    hitl_server.JWT_SECRET = "test-jwt-secret-for-unit-tests"
    hitl_server.JWT_EXPIRE_HOURS = 24

    return hitl_server


@pytest.fixture
def hitl_client(hitl_app):
    """Return a test client for the HITL FastAPI app."""
    from starlette.testclient import TestClient
    # Skip lifespan (it tries to connect to DB)
    return TestClient(hitl_app.app, raise_server_exceptions=False)


@pytest.fixture
def auth_headers(hitl_app):
    """Return valid JWT Authorization headers for a member user."""
    token = hitl_app.create_token("1", "user@test.com", "member", ["team1"])
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def admin_headers(hitl_app):
    """Return valid JWT Authorization headers for an admin user."""
    token = hitl_app.create_token("99", "admin@test.com", "admin", ["team1", "team2"])
    return {"Authorization": f"Bearer {token}"}
