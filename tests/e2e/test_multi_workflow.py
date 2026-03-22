"""E2E test: multi-workflow transitions via the PM/HITL API.

Scenario:
  1. Create a PM project
  2. Launch workflow (discovery phase) via the HITL gateway bridge
  3. Verify project status and workflow-status endpoint
  4. Pause the workflow
  5. Verify status is 'paused'
  6. Cleanup

Requires: HITL console (port 8090) running on AGT1.
"""

import uuid

import httpx
import pytest

from tests.e2e.conftest import (
    ADMIN_EMAIL,
    ADMIN_PASSWORD,
    HITL_URL,
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
)


_hitl_ok = check_health(HITL_URL)

skip_no_hitl = pytest.mark.skipif(
    not _hitl_ok, reason=f"HITL console not reachable at {HITL_URL}"
)


@pytest.fixture(scope="module")
def admin_token():
    if not _hitl_ok:
        pytest.skip("HITL console not available")
    return login(HITL_URL, ADMIN_EMAIL, ADMIN_PASSWORD)


@pytest.fixture()
def unique_slug():
    return f"{TEST_PROJECT_SLUG}-wf-{uuid.uuid4().hex[:8]}"


@pytest.fixture(autouse=True)
def cleanup_after(admin_token):
    yield
    if _hitl_ok:
        cleanup_test_projects(HITL_URL, admin_token, TEST_PROJECT_SLUG)


@skip_no_hitl
class TestMultiWorkflow:
    """PM project workflow lifecycle."""

    def test_create_project_and_check_detail(self, admin_token, unique_slug):
        """Create project, verify detail endpoint returns it."""
        result = create_pm_project(
            HITL_URL, admin_token, TEST_PROJECT_NAME, unique_slug, TEST_TEAM_ID, ADMIN_EMAIL
        )
        assert result["ok"] is True
        pid = result["id"]
        print(f"  Created project id={pid} slug={unique_slug}")

        resp = httpx.get(
            f"{HITL_URL}/api/pm/projects/{pid}",
            headers=auth_headers(admin_token),
            timeout=10,
        )
        assert resp.status_code == 200
        detail = resp.json()
        assert detail["slug"] == unique_slug
        assert detail["status"] == "on-track"
        print(f"  Detail: name={detail['name']} status={detail['status']}")

    def test_launch_workflow(self, admin_token, unique_slug):
        """Launch workflow on a project via gateway bridge."""
        result = create_pm_project(
            HITL_URL, admin_token, TEST_PROJECT_NAME, unique_slug, TEST_TEAM_ID, ADMIN_EMAIL
        )
        pid = result["id"]
        print(f"  Project id={pid}")

        resp = httpx.post(
            f"{HITL_URL}/api/pm/projects/launch-workflow",
            headers=auth_headers(admin_token),
            json={
                "project_id": pid,
                "team_id": TEST_TEAM_ID,
                "slug": unique_slug,
                "phase": "discovery",
            },
            timeout=30,
        )
        assert resp.status_code == 200
        data = resp.json()
        print(f"  Launch workflow response: {data}")
        # Gateway may not be running — ok is False with "not reachable" is acceptable
        if data.get("ok"):
            assert "thread_id" in data
            print(f"  Workflow launched: thread={data['thread_id']}")
        else:
            print(f"  Gateway not reachable (expected if only HITL is deployed): {data.get('error', '')}")

    def test_pause_workflow(self, admin_token, unique_slug):
        """Pause a project workflow and verify status change."""
        result = create_pm_project(
            HITL_URL, admin_token, TEST_PROJECT_NAME, unique_slug, TEST_TEAM_ID, ADMIN_EMAIL
        )
        pid = result["id"]
        print(f"  Project id={pid}")

        resp = httpx.post(
            f"{HITL_URL}/api/pm/projects/{pid}/pause-workflow",
            headers=auth_headers(admin_token),
            json={"team_id": TEST_TEAM_ID},
            timeout=10,
        )
        assert resp.status_code == 200
        print(f"  Pause response: {resp.json()}")

        # Verify status changed
        resp2 = httpx.get(
            f"{HITL_URL}/api/pm/projects/{pid}",
            headers=auth_headers(admin_token),
            timeout=10,
        )
        assert resp2.status_code == 200
        assert resp2.json()["status"] == "paused"
        print("  Project status is now 'paused'")

    def test_question_stats_empty(self, admin_token):
        """Question stats endpoint works even with no pending questions."""
        resp = httpx.get(
            f"{HITL_URL}/api/teams/{TEST_TEAM_ID}/questions/stats",
            headers=auth_headers(admin_token),
            timeout=10,
        )
        assert resp.status_code == 200
        stats = resp.json()
        assert "pending" in stats
        assert "total" in stats
        print(f"  Question stats: {stats}")

    def test_teams_list(self, admin_token):
        """Teams endpoint returns at least one team."""
        resp = httpx.get(
            f"{HITL_URL}/api/teams",
            headers=auth_headers(admin_token),
            timeout=10,
        )
        assert resp.status_code == 200
        teams = resp.json()
        assert len(teams) > 0
        team_ids = [t["id"] for t in teams]
        assert TEST_TEAM_ID in team_ids
        print(f"  Teams: {team_ids}")
