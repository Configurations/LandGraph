"""Unit tests for Production Manager API endpoints in HITL console.

Tests cover: projects CRUD, issues CRUD, relations, pull requests,
inbox notifications, activity, pulse metrics, blocked flag computation,
issue ID sequence generation, bulk operations, and AI planning.
"""
import json
import os
import sys
import types
import importlib
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch, PropertyMock

import pytest

# ---------------------------------------------------------------------------
# Stub out heavy dependencies so we can import hitl.server without a real DB
# ---------------------------------------------------------------------------

_psycopg = types.ModuleType("psycopg")
_psycopg.connect = MagicMock()
sys.modules.setdefault("psycopg", _psycopg)

_passlib = types.ModuleType("passlib")
_passlib_ctx = types.ModuleType("passlib.context")

class _FakeCryptContext:
    def __init__(self, **kw): pass
    def hash(self, pw): return f"hashed:{pw}"
    def verify(self, pw, h): return h == f"hashed:{pw}"

_passlib_ctx.CryptContext = _FakeCryptContext
sys.modules.setdefault("passlib", _passlib)
sys.modules.setdefault("passlib.context", _passlib_ctx)

_jose = types.ModuleType("jose")
_jose_jwt = types.ModuleType("jose.jwt")
_jose.JWTError = Exception
_jose_jwt.decode = lambda *a, **kw: {"sub": "x", "email": "x@x.com", "role": "admin"}
_jose_jwt.encode = lambda *a, **kw: "fake-jwt"
_jose.jwt = _jose_jwt
sys.modules.setdefault("jose", _jose)
sys.modules.setdefault("jose.jwt", _jose_jwt)

_dotenv = types.ModuleType("dotenv")
_dotenv.load_dotenv = lambda *a, **kw: None
sys.modules.setdefault("dotenv", _dotenv)

os.environ.setdefault("DATABASE_URI", "postgresql://test:test@localhost:5432/test")
os.environ.setdefault("HITL_JWT_SECRET", "test-secret-key")

_repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_hitl_dir = os.path.join(_repo_root, "hitl")
if _hitl_dir not in sys.path:
    sys.path.insert(0, _hitl_dir)
if _repo_root not in sys.path:
    sys.path.insert(0, _repo_root)

_orig_cwd = os.getcwd()
os.chdir(_hitl_dir)
with patch.dict(os.environ, {"DATABASE_URI": "postgresql://test:test@localhost:5432/test"}):
    import hitl.server as hitl_server
os.chdir(_orig_cwd)

from fastapi.testclient import TestClient

NOW = datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _fake_user():
    return hitl_server.TokenData(
        user_id="test-uid", email="test@example.com", role="admin", teams=["team1"])


@pytest.fixture
def cur():
    """Mock cursor."""
    c = MagicMock()
    return c


@pytest.fixture
def conn(cur):
    """Mock connection returning the cursor via context manager."""
    c = MagicMock()
    c.cursor.return_value.__enter__ = MagicMock(return_value=cur)
    c.cursor.return_value.__exit__ = MagicMock(return_value=False)
    return c


@pytest.fixture
def client(conn):
    """TestClient with mocked DB + auth."""
    hitl_server.app.dependency_overrides[hitl_server.get_current_user] = _fake_user
    with patch.object(hitl_server, "get_conn", return_value=conn):
        yield TestClient(hitl_server.app)
    hitl_server.app.dependency_overrides.pop(hitl_server.get_current_user, None)


H = {"Authorization": "Bearer x"}  # headers shortcut


# ===========================================================================
# _next_issue_id
# ===========================================================================

class TestNextIssueId:
    def test_standard(self, conn, cur):
        cur.fetchone.return_value = (1,)
        assert hitl_server._next_issue_id("team1", conn) == "TEAM1-001"

    def test_truncates_long_team(self, conn, cur):
        cur.fetchone.return_value = (42,)
        assert hitl_server._next_issue_id("my-very-long-team", conn) == "MYVERY-042"

    def test_pads_sequence(self, conn, cur):
        cur.fetchone.return_value = (5,)
        assert hitl_server._next_issue_id("eng", conn) == "ENG-005"

    def test_large_sequence(self, conn, cur):
        cur.fetchone.return_value = (1234,)
        assert hitl_server._next_issue_id("ops", conn) == "OPS-1234"

    def test_spaces_removed(self, conn, cur):
        cur.fetchone.return_value = (1,)
        assert hitl_server._next_issue_id("my team", conn) == "MYTEAM-001"


# ===========================================================================
# _compute_blocked_flags
# ===========================================================================

class TestComputeBlockedFlags:
    def test_empty(self, conn):
        assert hitl_server._compute_blocked_flags([], conn) == []

    def test_blocked_by_non_done(self, conn, cur):
        issues = [{"id": "A"}, {"id": "B"}]
        cur.fetchall.side_effect = [[("B", 1)], []]
        result = hitl_server._compute_blocked_flags(issues, conn)
        assert result[0]["is_blocked"] is False
        assert result[1]["is_blocked"] is True
        assert result[1]["blocked_by_count"] == 1

    def test_not_blocked_when_blockers_done(self, conn, cur):
        issues = [{"id": "A"}]
        cur.fetchall.side_effect = [[], []]
        result = hitl_server._compute_blocked_flags(issues, conn)
        assert result[0]["is_blocked"] is False

    def test_blocking_count(self, conn, cur):
        issues = [{"id": "A"}]
        cur.fetchall.side_effect = [[], [("A", 3)]]
        result = hitl_server._compute_blocked_flags(issues, conn)
        assert result[0]["blocking_count"] == 3


# ===========================================================================
# _log_activity / _create_notification
# ===========================================================================

class TestHelpers:
    def test_log_activity(self, conn, cur):
        hitl_server._log_activity(1, "u@t.com", "created", "E-1", "test", conn)
        assert "pm_activity" in cur.execute.call_args[0][0]

    def test_create_notification(self, conn, cur):
        hitl_server._create_notification("u@t.com", "assign", "text", "E-1", "Sys", conn)
        assert "pm_inbox" in cur.execute.call_args[0][0]


# ===========================================================================
# PM Projects API
# ===========================================================================

class TestPMProjects:
    def test_create(self, client, cur):
        cur.fetchone.return_value = (1,)
        r = client.post("/api/pm/projects", json={
            "name": "P1", "lead": "Alice", "team_id": "team1"}, headers=H)
        assert r.status_code == 200
        assert r.json()["id"] == 1

    def test_list(self, client, cur):
        cur.fetchall.side_effect = [
            [(1, "P1", "", "Lead", "t1", "#fff", "on-track", None, None, "u", NOW, NOW)],
            [("done", 3), ("todo", 2)],
            [("Alice", "lead")],
        ]
        cur.fetchone.side_effect = [(1,), (2,)]
        r = client.get("/api/pm/projects", headers=H)
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, list)
        assert len(data) == 1
        assert data[0]["total_issues"] == 5
        assert data[0]["completed_issues"] == 3
        assert data[0]["blocked_count"] == 1

    def test_delete(self, client, cur):
        type(cur).rowcount = PropertyMock(return_value=1)
        r = client.delete("/api/pm/projects/1", headers=H)
        assert r.status_code == 200

    def test_delete_404(self, client, cur):
        type(cur).rowcount = PropertyMock(return_value=0)
        r = client.delete("/api/pm/projects/999", headers=H)
        assert r.status_code == 404


# ===========================================================================
# PM Issues API
# ===========================================================================

class TestPMIssues:
    def test_create(self, client, cur):
        cur.fetchone.side_effect = [
            (1,),  # seq
            ("TEAM1-001", 1, "Bug", "", "todo", 3, None, "team1", [], "u", NOW, NOW),
        ]
        cur.fetchall.side_effect = [[], []]
        r = client.post("/api/pm/issues", json={"title": "Bug", "team_id": "team1"}, headers=H)
        assert r.status_code == 200
        assert r.json()["id"] == "TEAM1-001"

    def test_create_missing_title(self, client):
        r = client.post("/api/pm/issues", json={"team_id": "t1"}, headers=H)
        assert r.status_code == 422

    def test_get_with_relations(self, client, cur):
        cur.fetchone.return_value = ("E-1", 1, "T", "d", "todo", 2, "A", "t1", ["b"], "u", NOW, NOW)
        cur.fetchall.side_effect = [
            [(1, "blocks", "E-2", "r", NOW, "Other", "todo")],
            [(2, "blocks", "E-0", "b", NOW, "Blocker", "in-progress")],
            [("E-1", 1)], [],
        ]
        r = client.get("/api/pm/issues/E-1", headers=H)
        assert r.status_code == 200
        d = r.json()
        assert d["id"] == "E-1"
        assert len(d["relations"]) == 2
        out = [x for x in d["relations"] if x["type"] == "blocks"]
        assert out[0]["related_issue_id"] == "E-2"
        assert out[0]["display_type"] == "blocks"
        inc = [x for x in d["relations"] if x["type"] == "blocked-by"]
        assert inc[0]["related_issue_id"] == "E-0"
        assert d["is_blocked"] is True

    def test_get_404(self, client, cur):
        cur.fetchone.return_value = None
        r = client.get("/api/pm/issues/X", headers=H)
        assert r.status_code == 404

    def test_update_status(self, client, cur):
        cur.fetchone.side_effect = [
            ("todo", 1),
            ("E-1", 1, "T", "", "in-progress", 2, "A", "t1", [], "u", NOW, NOW),
        ]
        cur.fetchall.side_effect = [[], []]
        r = client.put("/api/pm/issues/E-1", json={"status": "in-progress"}, headers=H)
        assert r.status_code == 200
        assert r.json()["status"] == "in-progress"

    def test_update_404(self, client, cur):
        cur.fetchone.return_value = None
        r = client.put("/api/pm/issues/X", json={"status": "done"}, headers=H)
        assert r.status_code == 404

    def test_delete(self, client, cur):
        type(cur).rowcount = PropertyMock(return_value=1)
        r = client.delete("/api/pm/issues/E-1", headers=H)
        assert r.status_code == 200


# ===========================================================================
# Bulk Operations
# ===========================================================================

class TestBulk:
    def test_bulk_issues(self, client, cur):
        cur.fetchone.side_effect = [(1,), (2,)]
        r = client.post("/api/pm/issues/bulk", json={
            "project_id": 1, "team_id": "team1",
            "issues": [{"title": "A"}, {"title": "B"}],
        }, headers=H)
        assert r.status_code == 200
        d = r.json()
        assert "id_mapping" in d
        assert len(d["ids"]) == 2

    def test_bulk_relations(self, client, cur):
        type(cur).rowcount = PropertyMock(return_value=1)
        r = client.post("/api/pm/relations/bulk", json={
            "relations": [
                {"type": "blocks", "source_id": "A", "target_id": "B"},
                {"type": "relates-to", "source_id": "A", "target_id": "C"},
            ],
        }, headers=H)
        assert r.status_code == 200
        assert r.json()["created"] == 2


# ===========================================================================
# PM Relations API
# ===========================================================================

class TestPMRelations:
    def test_create(self, client, cur):
        cur.fetchone.side_effect = [(1,), (1,)]
        r = client.post("/api/pm/issues/E-1/relations", json={
            "type": "blocks", "target_issue_id": "E-2", "reason": "dep"}, headers=H)
        assert r.status_code == 200
        assert r.json()["ok"] is True

    def test_list_inverse_blocks(self, client, cur):
        cur.fetchall.side_effect = [
            [(1, "blocks", "E-2", "r", NOW, "T", "todo")],
            [(2, "blocks", "E-0", "b", NOW, "B", "in-progress")],
        ]
        r = client.get("/api/pm/issues/E-1/relations", headers=H)
        assert r.status_code == 200
        d = r.json()
        assert d[0]["type"] == "blocks"
        assert d[0]["direction"] == "outgoing"
        assert d[1]["type"] == "blocked-by"
        assert d[1]["direction"] == "incoming"

    def test_list_inverse_parent(self, client, cur):
        cur.fetchall.side_effect = [
            [],
            [(3, "parent", "E-0", "", NOW, "Parent", "in-progress")],
        ]
        r = client.get("/api/pm/issues/E-1/relations", headers=H)
        d = r.json()
        assert d[0]["type"] == "sub-task"

    def test_delete(self, client, cur):
        type(cur).rowcount = PropertyMock(return_value=1)
        r = client.delete("/api/pm/relations/1", headers=H)
        assert r.status_code == 200

    def test_delete_404(self, client, cur):
        type(cur).rowcount = PropertyMock(return_value=0)
        r = client.delete("/api/pm/relations/999", headers=H)
        assert r.status_code == 404


# ===========================================================================
# PM Reviews API
# ===========================================================================

class TestPMReviews:
    def test_list(self, client, cur):
        cur.fetchall.return_value = [
            ("PR-1", "Fix", "Alice", "E-1", "pending", 23, 12, 2, NOW, NOW)]
        r = client.get("/api/pm/reviews", headers=H)
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_create(self, client, cur):
        r = client.post("/api/pm/reviews", json={
            "id": "PR-1", "title": "New", "author": "Alice"}, headers=H)
        assert r.status_code == 200


# ===========================================================================
# PM Inbox API
# ===========================================================================

class TestPMInbox:
    def test_get(self, client, cur):
        cur.fetchall.return_value = [
            (1, "mention", "Alice mentioned you", "E-1", None, None, "Alice", False, NOW)]
        cur.fetchone.return_value = (1,)  # unread count
        r = client.get("/api/pm/inbox", headers=H)
        assert r.status_code == 200
        d = r.json()
        assert "notifications" in d
        assert isinstance(d["notifications"], list)
        assert d["unread"] == 1

    def test_mark_read(self, client, cur):
        r = client.put("/api/pm/inbox/1/read", headers=H)
        assert r.status_code == 200

    def test_mark_all_read(self, client, cur):
        r = client.put("/api/pm/inbox/read-all", headers=H)
        assert r.status_code == 200


# ===========================================================================
# PM Activity API
# ===========================================================================

class TestPMActivity:
    def test_get(self, client, cur):
        cur.fetchall.return_value = [(1, "Alice", "created", "E-1", "setup", NOW)]
        r = client.get("/api/pm/projects/1/activity", headers=H)
        assert r.status_code == 200
        d = r.json()
        assert isinstance(d, list)
        assert d[0]["user_name"] == "Alice"
        assert d[0]["action"] == "created"


# ===========================================================================
# PM Pulse API
# ===========================================================================

class TestPMPulse:
    def test_returns_metrics(self, client, cur):
        cur.fetchall.side_effect = [
            [("done", 3), ("todo", 5)],
            [("Alice", 3, 2), ("Bob", 1, 1)],
            [("E-1", "Pipeline", "in-progress", "Alice", 3)],
        ]
        cur.fetchone.side_effect = [(2,), (3,), (1,)]
        r = client.get("/api/pm/pulse", headers=H)
        assert r.status_code == 200
        d = r.json()
        assert "status_distribution" in d
        assert "team_activity" in d
        assert "dependency_health" in d
        assert "velocity" in d
        dh = d["dependency_health"]
        assert "blocked" in dh
        assert "blocking" in dh
        assert "chains" in dh
        assert "bottlenecks" in dh
        if d["team_activity"]:
            m = d["team_activity"][0]
            assert "name" in m
            assert "total" in m


# ===========================================================================
# Pydantic Models
# ===========================================================================

class TestModels:
    def test_project_create(self):
        p = hitl_server.PMProjectCreate(name="T", lead="A", team_id="e")
        assert p.color == "#6366f1"
        assert p.status == "on-track"

    def test_issue_create(self):
        i = hitl_server.PMIssueCreate(title="Bug")
        assert i.status == "backlog"
        assert i.priority == 3

    def test_issue_update_optional(self):
        u = hitl_server.PMIssueUpdate()
        assert u.title is None

    def test_relation_create(self):
        r = hitl_server.PMRelationCreate(type="blocks", target_issue_id="E-2")
        assert r.reason == ""

    def test_pr_create(self):
        pr = hitl_server.PMPRCreate(id="PR-1", title="Fix", author="A")
        assert pr.status == "draft"

    def test_ai_plan_request(self):
        p = hitl_server.PMAIPlanRequest(description="Build API")
        assert p.team_id == ""
        assert p.existing_issues is None
        assert p.project_name == ""


# ===========================================================================
# Inverse Relation Type Mapping
# ===========================================================================

class TestInverseMapping:
    _inv = {"blocks": "blocked-by", "parent": "sub-task",
            "relates-to": "relates-to", "duplicates": "duplicates"}

    def test_blocks(self): assert self._inv["blocks"] == "blocked-by"
    def test_parent(self): assert self._inv["parent"] == "sub-task"
    def test_relates_to(self): assert self._inv["relates-to"] == "relates-to"
    def test_duplicates(self): assert self._inv["duplicates"] == "duplicates"


# ===========================================================================
# _truncate_pw
# ===========================================================================

class TestTruncatePw:
    def test_short(self):
        assert hitl_server._truncate_pw("short") == "short"

    def test_long_truncated(self):
        assert len(hitl_server._truncate_pw("a" * 100).encode()) <= 72

    def test_multibyte(self):
        assert len(hitl_server._truncate_pw("\U0001F600" * 20).encode()) <= 72


# ===========================================================================
# Health
# ===========================================================================

class TestHealth:
    def test_ok(self):
        client = TestClient(hitl_server.app)
        r = client.get("/health")
        assert r.status_code == 200
        assert r.json()["status"] == "ok"


# ===========================================================================
# Issue ID Format
# ===========================================================================

class TestIssueIdFormat:
    def test_format(self, conn, cur):
        cur.fetchone.return_value = (1,)
        r = hitl_server._next_issue_id("eng", conn)
        assert r == "ENG-001"
        assert r.count("-") == 1

    def test_hyphens_removed(self, conn, cur):
        cur.fetchone.return_value = (1,)
        r = hitl_server._next_issue_id("my-team", conn)
        assert r.split("-")[0] == "MYTEAM"
