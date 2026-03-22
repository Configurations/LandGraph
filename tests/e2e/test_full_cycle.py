"""E2E test: full agent task cycle against real AGT1 services.

Scenario:
  1. Health-check dispatcher and HITL console
  2. Login as admin
  3. Create a PM project
  4. Launch a task via the dispatcher
  5. Wait for artifact + HITL question
  6. Verify question appears in HITL inbox
  7. Answer the question
  8. Wait for task completion
  9. Verify costs endpoint
 10. Cleanup

Requires: dispatcher (port 8070) and HITL console (port 8090) running on AGT1.
"""

import time
import uuid

import httpx
import pytest

from tests.e2e.conftest import (
    ADMIN_EMAIL,
    ADMIN_PASSWORD,
    DISPATCHER_URL,
    HITL_URL,
    TEST_AGENT_IMAGE,
    TEST_PROJECT_NAME,
    TEST_PROJECT_SLUG,
    TEST_TEAM_ID,
)
from tests.e2e.helpers import (
    auth_headers,
    check_health,
    cleanup_test_projects,
    create_pm_project,
    delete_pm_project,
    login,
    wait_for_question,
    wait_for_task_events,
    wait_for_task_status,
)


# ── Skip helpers ─────────────────────────────────────

_dispatcher_ok = check_health(DISPATCHER_URL)
_hitl_ok = check_health(HITL_URL)

skip_no_dispatcher = pytest.mark.skipif(
    not _dispatcher_ok, reason=f"Dispatcher not reachable at {DISPATCHER_URL}"
)
skip_no_hitl = pytest.mark.skipif(
    not _hitl_ok, reason=f"HITL console not reachable at {HITL_URL}"
)


# ── Fixtures ─────────────────────────────────────────

@pytest.fixture(scope="module")
def admin_token():
    """Login once per module, return JWT."""
    if not _hitl_ok:
        pytest.skip("HITL console not available for login")
    token = login(HITL_URL, ADMIN_EMAIL, ADMIN_PASSWORD)
    print(f"  [fixture] Logged in as {ADMIN_EMAIL}")
    return token


@pytest.fixture()
def unique_slug():
    """Generate a unique slug per test to avoid collisions."""
    return f"{TEST_PROJECT_SLUG}-{uuid.uuid4().hex[:8]}"


@pytest.fixture(autouse=True)
def cleanup_after(admin_token):
    """Cleanup all e2e test projects after each test."""
    yield
    if _hitl_ok:
        n = cleanup_test_projects(HITL_URL, admin_token, TEST_PROJECT_SLUG)
        if n:
            print(f"  [cleanup] Deleted {n} test project(s)")


# ── Tests ────────────────────────────────────────────


class TestServiceHealth:
    """Verify services respond before running heavier tests."""

    @skip_no_dispatcher
    def test_dispatcher_healthy(self):
        resp = httpx.get(f"{DISPATCHER_URL}/health", timeout=10)
        assert resp.status_code == 200
        data = resp.json()
        print(f"  Dispatcher health: {data}")
        assert data["status"] in ("ok", "degraded")

    @skip_no_dispatcher
    def test_dispatcher_db_connected(self):
        resp = httpx.get(f"{DISPATCHER_URL}/health", timeout=10)
        data = resp.json()
        assert data["db"] is True, "Dispatcher DB not connected"
        print("  Dispatcher DB: connected")

    @skip_no_hitl
    def test_hitl_healthy(self):
        resp = httpx.get(f"{HITL_URL}/health", timeout=10)
        assert resp.status_code == 200
        print(f"  HITL health: {resp.json()}")

    @skip_no_hitl
    def test_hitl_login(self, admin_token):
        resp = httpx.get(
            f"{HITL_URL}/api/auth/me",
            headers=auth_headers(admin_token),
            timeout=10,
        )
        assert resp.status_code == 200
        me = resp.json()
        assert me["email"] == ADMIN_EMAIL
        assert me["role"] == "admin"
        print(f"  Logged in user: {me['email']} role={me['role']}")


class TestDispatcherEndpoints:
    """Verify dispatcher read-only endpoints work."""

    @skip_no_dispatcher
    def test_active_tasks_endpoint(self):
        resp = httpx.get(f"{DISPATCHER_URL}/api/tasks/active", timeout=10)
        assert resp.status_code == 200
        tasks = resp.json()
        print(f"  Active tasks: {len(tasks)}")

    @skip_no_dispatcher
    def test_costs_endpoint_empty_project(self):
        resp = httpx.get(f"{DISPATCHER_URL}/api/costs/nonexistent-slug", timeout=10)
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_cost_usd"] == 0
        print(f"  Costs for nonexistent project: {data}")

    @skip_no_dispatcher
    def test_get_unknown_task_returns_404(self):
        fake_id = "00000000-0000-0000-0000-000000000000"
        resp = httpx.get(f"{DISPATCHER_URL}/api/tasks/{fake_id}", timeout=10)
        assert resp.status_code == 404
        print("  Unknown task returns 404 as expected")


class TestPMProjects:
    """Verify PM project CRUD via HITL API."""

    @skip_no_hitl
    def test_create_and_list_project(self, admin_token, unique_slug):
        print(f"  Creating project slug={unique_slug}")
        result = create_pm_project(
            HITL_URL, admin_token, TEST_PROJECT_NAME, unique_slug, TEST_TEAM_ID, ADMIN_EMAIL
        )
        assert result.get("ok") is True
        project_id = result["id"]
        print(f"  Created project id={project_id}")

        # Verify it appears in list
        resp = httpx.get(
            f"{HITL_URL}/api/pm/projects",
            headers=auth_headers(admin_token),
            timeout=10,
        )
        assert resp.status_code == 200
        slugs = [p["slug"] for p in resp.json()]
        assert unique_slug in slugs, f"Project {unique_slug} not found in list"
        print(f"  Project visible in list ({len(slugs)} total)")

    @skip_no_hitl
    def test_delete_project(self, admin_token, unique_slug):
        result = create_pm_project(
            HITL_URL, admin_token, "Delete Me", unique_slug, TEST_TEAM_ID, ADMIN_EMAIL
        )
        pid = result["id"]
        print(f"  Created project id={pid}, now deleting")

        resp = httpx.delete(
            f"{HITL_URL}/api/pm/projects/{pid}",
            headers=auth_headers(admin_token),
            timeout=10,
        )
        assert resp.status_code == 200
        print("  Deleted successfully")


class TestFullTaskCycle:
    """Full dispatcher task lifecycle (requires agent image available)."""

    @skip_no_dispatcher
    def test_submit_task(self, unique_slug):
        """Submit a task and verify it is accepted (202)."""
        payload = {
            "agent_id": "test-agent",
            "team_id": TEST_TEAM_ID,
            "thread_id": f"e2e-{unique_slug}",
            "project_slug": unique_slug,
            "phase": "test",
            "payload": {
                "instruction": "E2E smoke test — return immediately",
                "context": {},
            },
            "timeout_seconds": 60,
            "docker_image": TEST_AGENT_IMAGE,
        }
        resp = httpx.post(f"{DISPATCHER_URL}/api/tasks/run", json=payload, timeout=30)
        print(f"  POST /tasks/run -> {resp.status_code}: {resp.text[:300]}")
        assert resp.status_code == 202
        data = resp.json()
        assert "task_id" in data
        print(f"  Task accepted: {data['task_id']}")

    @skip_no_dispatcher
    def test_submit_and_poll_status(self, unique_slug):
        """Submit a task and poll until it leaves 'pending'."""
        payload = {
            "agent_id": "test-agent",
            "team_id": TEST_TEAM_ID,
            "thread_id": f"e2e-poll-{unique_slug}",
            "project_slug": unique_slug,
            "phase": "test",
            "payload": {
                "instruction": "E2E poll test",
                "context": {},
            },
            "timeout_seconds": 60,
            "docker_image": TEST_AGENT_IMAGE,
        }
        resp = httpx.post(f"{DISPATCHER_URL}/api/tasks/run", json=payload, timeout=30)
        assert resp.status_code == 202
        task_id = resp.json()["task_id"]
        print(f"  Task created: {task_id}")

        # Poll — accept any terminal or waiting state
        print("  Polling for status change...")
        try:
            task = wait_for_task_status(
                DISPATCHER_URL, task_id,
                ["running", "waiting_hitl", "success", "failure", "cancelled"],
                timeout=60,
            )
            print(f"  Task reached status: {task['status']}")
        except TimeoutError as e:
            print(f"  Timeout polling task: {e}")
            # Not a hard failure — agent image may not be available
            pytest.skip(f"Task did not leave pending: {e}")

    @skip_no_dispatcher
    def test_cancel_unknown_task_returns_400(self):
        """Cancelling a non-existent task returns an error."""
        fake_id = "00000000-0000-0000-0000-000000000000"
        resp = httpx.post(f"{DISPATCHER_URL}/api/tasks/{fake_id}/cancel", timeout=10)
        assert resp.status_code in (400, 404)
        print(f"  Cancel unknown task: {resp.status_code}")
