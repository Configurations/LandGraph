"""Tests des endpoints HITL via TestClient avec DB mockee.

La strategie : on importe hitl/server.py en patchant get_conn() pour
retourner un FakeConn avec des resultats pre-programmes.
"""
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

try:
    from starlette.testclient import TestClient
    _HAS_STARLETTE = True
except ImportError:
    _HAS_STARLETTE = False

try:
    from jose import jwt as jose_jwt
    _HAS_JOSE = True
except ImportError:
    _HAS_JOSE = False

pytestmark = pytest.mark.skipif(
    not (_HAS_STARLETTE and _HAS_JOSE),
    reason="starlette ou python-jose manquant",
)

# ── Fake DB layer ────────────────────────────────

class MultiFakeCursor:
    """Curseur qui retourne des resultats differents pour chaque execute()."""

    def __init__(self, result_sets=None):
        """result_sets: list of lists — one per execute() call."""
        self._result_sets = list(result_sets or [[]])
        self._query_idx = -1
        self._row_idx = 0
        self.rowcount = 1
        self.queries = []

    def execute(self, query, params=None):
        self.queries.append((query, params))
        self._query_idx += 1
        self._row_idx = 0

    def _current_results(self):
        if 0 <= self._query_idx < len(self._result_sets):
            return self._result_sets[self._query_idx]
        return []

    def fetchone(self):
        results = self._current_results()
        if self._row_idx < len(results):
            r = results[self._row_idx]
            self._row_idx += 1
            return r
        return None

    def fetchall(self):
        results = self._current_results()
        rows = results[self._row_idx:]
        self._row_idx = len(results)
        return rows

    def __enter__(self):
        return self

    def __exit__(self, *a):
        pass


class FakeCursor(MultiFakeCursor):
    """Curseur simple — memes resultats pour tous les execute()."""

    def __init__(self, results=None):
        # Wrap single result set to be returned for every query
        self._single_results = list(results or [])
        super().__init__([self._single_results])

    def execute(self, query, params=None):
        self.queries.append((query, params))
        self._query_idx = 0  # always point to the single result set
        self._row_idx = 0  # reset to start of same results


class FakeConn:
    def __init__(self, cursor=None):
        self._cursor = cursor or FakeCursor()

    def cursor(self):
        return self._cursor

    def close(self):
        pass


# ── Import HITL server (with mocked heavy deps) ──

_hitl_dir = Path(__file__).resolve().parent.parent.parent / "hitl"
_JWT_SECRET = "test-jwt-secret"


def _import_hitl_server(tmp_path):
    """Import hitl/server.py with mocked psycopg, passlib, etc."""
    # Setup config files
    config_dir = tmp_path / "config"
    config_dir.mkdir(exist_ok=True)
    teams_dir = config_dir / "Teams"
    teams_dir.mkdir(exist_ok=True)
    team1_dir = teams_dir / "Team1"
    team1_dir.mkdir(exist_ok=True)
    (teams_dir / "teams.json").write_text(json.dumps({
        "teams": [{"id": "team1", "name": "Team 1", "directory": "Team1"}]
    }))
    (config_dir / "hitl.json").write_text(json.dumps({
        "auth": {"jwt_expire_hours": 24, "allow_registration": True},
        "google_oauth": {"enabled": True, "client_id": "test-client-id", "allowed_domains": ["test.com"]},
    }))
    (team1_dir / "agents_registry.json").write_text(json.dumps({
        "agents": {
            "orchestrator": {"name": "Orchestrateur", "type": "orchestrator"},
            "lead_dev": {"name": "Lead Dev", "type": "single"},
        }
    }))

    # Add hitl dir to path
    if str(_hitl_dir) not in sys.path:
        sys.path.insert(0, str(_hitl_dir))

    # Remove cached server module
    if "server" in sys.modules:
        del sys.modules["server"]

    old_cwd = os.getcwd()
    os.chdir(str(_hitl_dir))  # so StaticFiles("static") works
    try:
        with patch.dict(os.environ, {
            "DATABASE_URI": "postgresql://test:test@localhost/test",
            "HITL_JWT_SECRET": _JWT_SECRET,
        }):
            import server as hitl_server
    finally:
        os.chdir(old_cwd)

    hitl_server.JWT_SECRET = _JWT_SECRET
    hitl_server._CONFIG_DIR = str(config_dir)
    return hitl_server


def _make_token(user_id="1", email="user@test.com", role="member", teams=None):
    payload = {
        "sub": user_id, "email": email, "role": role,
        "teams": teams or ["team1"],
        "exp": datetime.now(timezone.utc) + timedelta(hours=24),
    }
    return jose_jwt.encode(payload, _JWT_SECRET, algorithm="HS256")


# ── Fixtures ──────────────────────────────────────


@pytest.fixture
def hitl(tmp_path):
    return _import_hitl_server(tmp_path)


@pytest.fixture
def client(hitl):
    return TestClient(hitl.app, raise_server_exceptions=False)


@pytest.fixture
def member_headers():
    return {"Authorization": f"Bearer {_make_token()}"}


@pytest.fixture
def admin_headers():
    return {"Authorization": f"Bearer {_make_token('99', 'admin@test.com', 'admin', ['team1', 'team2'])}"}


# ── Auth endpoints ────────────────────────────────


class TestHitlLogin:

    def test_login_success(self, hitl, client):
        """Login avec email/password correct."""
        user_row = (1, "user@test.com", "$2b$12$fakehash", "User", "member", True, "local")
        team_rows = [("team1", "member")]
        cursor = FakeCursor([user_row, *team_rows])

        with patch.object(hitl, "get_conn", return_value=FakeConn(cursor)):
            with patch.object(hitl.pwd_ctx, "verify", return_value=True):
                r = client.post("/api/auth/login", json={"email": "user@test.com", "password": "pass123"})

        assert r.status_code == 200
        data = r.json()
        assert "token" in data
        assert data["user"]["email"] == "user@test.com"

    def test_login_wrong_password(self, hitl, client):
        user_row = (1, "user@test.com", "$2b$12$hash", "User", "member", True, "local")
        cursor = FakeCursor([user_row])

        with patch.object(hitl, "get_conn", return_value=FakeConn(cursor)):
            with patch.object(hitl.pwd_ctx, "verify", return_value=False):
                r = client.post("/api/auth/login", json={"email": "user@test.com", "password": "wrong"})

        assert r.status_code == 401

    def test_login_unknown_email(self, hitl, client):
        cursor = FakeCursor([])  # no user found

        with patch.object(hitl, "get_conn", return_value=FakeConn(cursor)):
            r = client.post("/api/auth/login", json={"email": "nobody@test.com", "password": "pass"})

        assert r.status_code == 401

    def test_login_google_user_rejected(self, hitl, client):
        """Un utilisateur Google ne peut pas se connecter avec un password."""
        user_row = (1, "guser@test.com", None, "GUser", "member", True, "google")
        cursor = FakeCursor([user_row])

        with patch.object(hitl, "get_conn", return_value=FakeConn(cursor)):
            r = client.post("/api/auth/login", json={"email": "guser@test.com", "password": "pass"})

        assert r.status_code == 400

    def test_login_undefined_role(self, hitl, client):
        user_row = (1, "new@test.com", "$2b$hash", "New", "undefined", True, "local")
        cursor = FakeCursor([user_row])

        with patch.object(hitl, "get_conn", return_value=FakeConn(cursor)):
            with patch.object(hitl.pwd_ctx, "verify", return_value=True):
                r = client.post("/api/auth/login", json={"email": "new@test.com", "password": "pass"})

        assert r.status_code == 403

    def test_login_inactive_user(self, hitl, client):
        user_row = (1, "u@t.com", "$2b$hash", "U", "member", False, "local")
        cursor = FakeCursor([user_row])

        with patch.object(hitl, "get_conn", return_value=FakeConn(cursor)):
            with patch.object(hitl.pwd_ctx, "verify", return_value=True):
                r = client.post("/api/auth/login", json={"email": "u@t.com", "password": "pass"})

        assert r.status_code == 403


class TestHitlRegister:

    def test_register_success(self, hitl, client):
        # Query 1: SELECT existing user → None, Query 2: INSERT → returns id
        cursor = MultiFakeCursor([[], [(42,)]])

        with patch.object(hitl, "get_conn", return_value=FakeConn(cursor)):
            with patch.object(hitl.pwd_ctx, "hash", return_value="$2b$12$mockedhash"):
                with patch.object(hitl, "_send_reset_email", return_value=True):
                    r = client.post("/api/auth/register", json={"email": "new@valid.com", "culture": "fr"})

        assert r.status_code == 200
        assert r.json()["ok"] is True

    def test_register_invalid_email(self, hitl, client):
        r = client.post("/api/auth/register", json={"email": "not-an-email", "culture": "fr"})
        assert r.status_code == 400

    def test_register_duplicate(self, hitl, client):
        cursor = FakeCursor([(1,)])  # user exists

        with patch.object(hitl, "get_conn", return_value=FakeConn(cursor)):
            r = client.post("/api/auth/register", json={"email": "exists@test.com"})

        assert r.status_code == 409


class TestHitlGoogleAuth:

    def test_google_client_id(self, hitl, client):
        r = client.get("/api/auth/google/client-id")
        assert r.status_code == 200
        # May return empty or configured client_id
        assert "client_id" in r.json()

    def test_google_login_new_user(self, hitl, client):
        """Nouveau user Google → cree avec role=undefined → 403."""
        google_data = {
            "aud": "test-client-id",
            "email": "new@test.com",
            "email_verified": "true",
            "name": "New User",
        }
        # Query 1: SELECT existing → None, Query 2: INSERT → id, Query 3: teams
        cursor = MultiFakeCursor([[], [(99,)]])

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = google_data

        import httpx as _httpx_mod
        with patch.object(hitl, "get_conn", return_value=FakeConn(cursor)):
            with patch.object(_httpx_mod, "get", return_value=mock_resp):
                with patch.object(hitl, "_load_hitl_config", return_value={
                    "google_oauth": {"enabled": True, "client_id": "test-client-id", "allowed_domains": ["test.com"]},
                }):
                    r = client.post("/api/auth/google", json={"credential": "fake-token"})

        assert r.status_code == 403  # undefined role

    def test_google_domain_restriction(self, hitl, client):
        """Email d'un domaine non autorise → 403."""
        google_data = {
            "aud": "test-client-id",
            "email": "user@forbidden.com",
            "email_verified": "true",
        }
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = google_data

        import httpx as _httpx_mod
        with patch.object(_httpx_mod, "get", return_value=mock_resp):
            with patch.object(hitl, "_load_hitl_config", return_value={
                "google_oauth": {"enabled": True, "client_id": "test-client-id", "allowed_domains": ["test.com"]},
            }):
                r = client.post("/api/auth/google", json={"credential": "fake-token"})

        assert r.status_code == 403


class TestHitlResetPassword:

    def test_reset_success(self, hitl, client):
        user_row = (1, "$2b$12$oldhash", "local")
        cursor = FakeCursor([user_row])

        with patch.object(hitl, "get_conn", return_value=FakeConn(cursor)):
            with patch.object(hitl.pwd_ctx, "verify", return_value=True):
                with patch.object(hitl.pwd_ctx, "hash", return_value="$2b$12$newhash"):
                    r = client.post("/api/auth/reset-password", json={
                        "email": "user@test.com",
                        "old_password": "old",
                        "new_password": "newpass123",
                    })

        assert r.status_code == 200

    def test_reset_short_password(self, hitl, client):
        r = client.post("/api/auth/reset-password", json={
            "email": "u@t.com", "old_password": "old", "new_password": "abc",
        })
        assert r.status_code == 400

    def test_reset_google_user(self, hitl, client):
        user_row = (1, None, "google")
        cursor = FakeCursor([user_row])

        with patch.object(hitl, "get_conn", return_value=FakeConn(cursor)):
            r = client.post("/api/auth/reset-password", json={
                "email": "g@test.com", "old_password": "old", "new_password": "newpass123",
            })

        assert r.status_code == 400


class TestHitlMe:

    def test_get_me(self, hitl, client, member_headers):
        user_row = (1, "user@test.com", "User", "member")
        team_rows = [("team1", "member")]
        cursor = FakeCursor([user_row, *team_rows])

        with patch.object(hitl, "get_conn", return_value=FakeConn(cursor)):
            r = client.get("/api/auth/me", headers=member_headers)

        assert r.status_code == 200
        assert r.json()["email"] == "user@test.com"

    def test_get_me_no_token(self, hitl, client):
        r = client.get("/api/auth/me")
        assert r.status_code == 401


# ── Teams ─────────────────────────────────────────


class TestHitlTeams:

    def test_list_teams(self, hitl, client, member_headers):
        r = client.get("/api/teams", headers=member_headers)
        assert r.status_code == 200
        teams = r.json()
        ids = [t["id"] for t in teams]
        assert "team1" in ids


# ── Questions ─────────────────────────────────────


class TestHitlQuestions:

    def _make_q_row(self, qid=1, status="pending"):
        dt = datetime(2025, 1, 15, 10, 0, tzinfo=timezone.utc)
        return (
            qid, "t-1", "lead_dev", "team1", "approval", "Valider ?",
            {}, "discord", status, None, None, None,
            dt, None, None, None, 0,
        )

    def test_list_questions(self, hitl, client, member_headers):
        cursor = FakeCursor([self._make_q_row(1), self._make_q_row(2)])

        with patch.object(hitl, "get_conn", return_value=FakeConn(cursor)):
            r = client.get("/api/teams/team1/questions", headers=member_headers)

        assert r.status_code == 200
        assert len(r.json()) == 2

    def test_list_questions_forbidden_team(self, hitl, client, member_headers):
        with patch.object(hitl, "get_conn", return_value=FakeConn()):
            r = client.get("/api/teams/team99/questions", headers=member_headers)

        assert r.status_code == 403

    def test_question_stats(self, hitl, client, member_headers):
        # Query 1: GROUP BY status, Query 2: relance count
        cursor = MultiFakeCursor([
            [("pending", 3), ("answered", 7)],
            [(1,)],
        ])

        with patch.object(hitl, "get_conn", return_value=FakeConn(cursor)):
            r = client.get("/api/teams/team1/questions/stats", headers=member_headers)

        assert r.status_code == 200
        data = r.json()
        assert "pending" in data

    def test_get_single_question(self, hitl, client, member_headers):
        cursor = FakeCursor([self._make_q_row(42)])

        with patch.object(hitl, "get_conn", return_value=FakeConn(cursor)):
            r = client.get("/api/questions/42", headers=member_headers)

        assert r.status_code == 200
        assert r.json()["id"] == "42"

    def test_answer_question(self, hitl, client, member_headers):
        q_row = ("team1", "pending")  # team_id, status check
        cursor = FakeCursor([q_row])

        with patch.object(hitl, "get_conn", return_value=FakeConn(cursor)):
            r = client.post("/api/questions/1/answer", headers=member_headers, json={
                "response": "Approuve", "action": "approve",
            })

        assert r.status_code == 200
        assert r.json()["ok"] is True

    def test_answer_already_answered(self, hitl, client, member_headers):
        q_row = ("team1", "answered")  # already answered
        cursor = FakeCursor([q_row])

        with patch.object(hitl, "get_conn", return_value=FakeConn(cursor)):
            r = client.post("/api/questions/1/answer", headers=member_headers, json={
                "response": "Late", "action": "answer",
            })

        assert r.status_code == 400

    def test_answer_wrong_team(self, hitl, client, member_headers):
        q_row = ("team99", "pending")  # team user doesn't have access to
        cursor = FakeCursor([q_row])

        with patch.object(hitl, "get_conn", return_value=FakeConn(cursor)):
            r = client.post("/api/questions/1/answer", headers=member_headers, json={
                "response": "Nope", "action": "answer",
            })

        assert r.status_code == 403


# ── Agents ────────────────────────────────────────


class TestHitlAgents:

    def test_list_agents(self, hitl, client, member_headers):
        stats_rows = [("lead_dev", 2, 5, datetime(2025, 1, 15, tzinfo=timezone.utc))]
        cursor = FakeCursor(stats_rows)

        with patch.object(hitl, "get_conn", return_value=FakeConn(cursor)):
            r = client.get("/api/teams/team1/agents", headers=member_headers)

        assert r.status_code == 200
        agents = r.json()
        assert any(a["id"] == "lead_dev" for a in agents)

    def test_list_agents_forbidden(self, hitl, client, member_headers):
        with patch.object(hitl, "get_conn", return_value=FakeConn()):
            r = client.get("/api/teams/team99/agents", headers=member_headers)

        assert r.status_code == 403


# ── Members ───────────────────────────────────────


class TestHitlMembers:

    def test_list_members(self, hitl, client, member_headers):
        member_rows = [
            (1, "user@test.com", "User", "member", "member", datetime(2025, 1, 15, tzinfo=timezone.utc), True),
        ]
        cursor = FakeCursor(member_rows)

        with patch.object(hitl, "get_conn", return_value=FakeConn(cursor)):
            r = client.get("/api/teams/team1/members", headers=member_headers)

        assert r.status_code == 200
        assert len(r.json()) == 1
        assert r.json()[0]["email"] == "user@test.com"

    def test_invite_member_new(self, hitl, client, member_headers):
        # First fetchone (check existing) returns None, second (INSERT) returns id
        cursor = FakeCursor()
        cursor.fetchone = MagicMock(side_effect=[None, (50,)])

        with patch.object(hitl, "get_conn", return_value=FakeConn(cursor)):
            with patch.object(hitl.pwd_ctx, "hash", return_value="$2b$hash"):
                r = client.post("/api/teams/team1/members", headers=member_headers, json={
                    "email": "new@test.com", "display_name": "New", "role": "member",
                })

        assert r.status_code == 200
        assert r.json()["ok"] is True

    def test_invite_member_existing(self, hitl, client, member_headers):
        cursor = FakeCursor()
        cursor.fetchone = MagicMock(return_value=(1,))  # user exists

        with patch.object(hitl, "get_conn", return_value=FakeConn(cursor)):
            r = client.post("/api/teams/team1/members", headers=member_headers, json={
                "email": "existing@test.com", "role": "member",
            })

        assert r.status_code == 200

    def test_remove_member_admin(self, hitl, client, admin_headers):
        cursor = FakeCursor()

        with patch.object(hitl, "get_conn", return_value=FakeConn(cursor)):
            r = client.delete("/api/teams/team1/members/1", headers=admin_headers)

        assert r.status_code == 200

    def test_remove_member_non_admin(self, hitl, client, member_headers):
        r = client.delete("/api/teams/team1/members/1", headers=member_headers)
        assert r.status_code == 403


# ── Chat ──────────────────────────────────────────


class TestHitlChat:

    def test_get_chat_history(self, hitl, client, member_headers):
        dt = datetime(2025, 1, 15, 10, 0, tzinfo=timezone.utc)
        rows = [
            (1, "user@test.com", "Hello", dt),
            (2, "lead_dev", "Hi there", dt),
        ]
        cursor = FakeCursor(rows)

        with patch.object(hitl, "get_conn", return_value=FakeConn(cursor)):
            r = client.get("/api/teams/team1/agents/lead_dev/chat", headers=member_headers)

        assert r.status_code == 200
        msgs = r.json()
        assert len(msgs) == 2
        assert msgs[0]["sender"] == "user@test.com"

    def test_send_chat_message(self, hitl, client, member_headers):
        cursor = FakeCursor()

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"output": "Agent reply"}

        import httpx as _httpx_mod
        with patch.object(hitl, "get_conn", return_value=FakeConn(cursor)):
            with patch.object(_httpx_mod, "post", return_value=mock_resp):
                r = client.post("/api/teams/team1/agents/lead_dev/chat", headers=member_headers, json={
                    "message": "Hello agent",
                })

        assert r.status_code == 200
        assert r.json()["reply"] == "Agent reply"

    def test_send_chat_gateway_error(self, hitl, client, member_headers):
        cursor = FakeCursor()

        import httpx as _httpx_mod
        with patch.object(hitl, "get_conn", return_value=FakeConn(cursor)):
            with patch.object(_httpx_mod, "post", side_effect=_httpx_mod.ConnectError("Connection refused")):
                r = client.post("/api/teams/team1/agents/lead_dev/chat", headers=member_headers, json={
                    "message": "Hello",
                })

        assert r.status_code == 200
        assert "pas accessible" in r.json()["reply"]

    def test_clear_chat(self, hitl, client, member_headers):
        cursor = FakeCursor()

        with patch.object(hitl, "get_conn", return_value=FakeConn(cursor)):
            r = client.delete("/api/teams/team1/agents/lead_dev/chat", headers=member_headers)

        assert r.status_code == 200

    def test_chat_forbidden_team(self, hitl, client, member_headers):
        with patch.object(hitl, "get_conn", return_value=FakeConn()):
            r = client.get("/api/teams/team99/agents/lead_dev/chat", headers=member_headers)

        assert r.status_code == 403


# ── Health & Version ──────────────────────────────


class TestHitlMisc:

    def test_health(self, hitl, client):
        r = client.get("/health")
        assert r.status_code == 200
        assert r.json()["status"] == "ok"

    def test_version(self, hitl, client):
        r = client.get("/api/version")
        assert r.status_code == 200
        assert "version" in r.json()
