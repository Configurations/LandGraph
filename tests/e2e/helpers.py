"""Shared helpers for e2e tests — HTTP calls, polling, auth, cleanup."""

import time
from typing import Optional

import httpx


def check_health(url: str, timeout: float = 10.0) -> bool:
    """Check if a service responds to /health."""
    try:
        resp = httpx.get(f"{url}/health", timeout=timeout)
        return resp.status_code == 200
    except Exception:
        return False


def login(hitl_url: str, email: str, password: str) -> str:
    """Login to HITL console and return JWT token."""
    resp = httpx.post(
        f"{hitl_url}/api/auth/login",
        json={"email": email, "password": password},
        timeout=10,
    )
    resp.raise_for_status()
    return resp.json()["token"]


def auth_headers(token: str) -> dict:
    """Return Authorization header dict."""
    return {"Authorization": f"Bearer {token}"}


def wait_for_task_status(
    dispatcher_url: str,
    task_id: str,
    target_statuses: list[str],
    timeout: float = 60.0,
    poll_interval: float = 2.0,
) -> dict:
    """Poll dispatcher until task reaches one of target_statuses or timeout."""
    deadline = time.time() + timeout
    last_status = "unknown"
    while time.time() < deadline:
        resp = httpx.get(f"{dispatcher_url}/api/tasks/{task_id}", timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            last_status = data.get("status", "unknown")
            if last_status in target_statuses:
                return data
        time.sleep(poll_interval)
    raise TimeoutError(
        f"Task {task_id} stuck at '{last_status}', expected {target_statuses} within {timeout}s"
    )


def wait_for_task_events(
    dispatcher_url: str,
    task_id: str,
    event_type: str,
    min_count: int = 1,
    timeout: float = 30.0,
) -> list[dict]:
    """Wait until at least min_count events of event_type appear for a task."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        resp = httpx.get(f"{dispatcher_url}/api/tasks/{task_id}/events", timeout=10)
        if resp.status_code == 200:
            events = [e for e in resp.json() if e.get("event_type") == event_type]
            if len(events) >= min_count:
                return events
        time.sleep(2)
    raise TimeoutError(
        f"Expected {min_count} '{event_type}' events for task {task_id} within {timeout}s"
    )


def wait_for_question(
    hitl_url: str,
    team_id: str,
    token: str,
    timeout: float = 30.0,
) -> dict:
    """Wait for a pending HITL question to appear in team inbox."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        resp = httpx.get(
            f"{hitl_url}/api/teams/{team_id}/questions?status=pending",
            headers=auth_headers(token),
            timeout=10,
        )
        if resp.status_code == 200:
            questions = resp.json()
            if questions:
                return questions[0]
        time.sleep(2)
    raise TimeoutError(f"No pending question in team {team_id} within {timeout}s")


def create_pm_project(
    hitl_url: str,
    token: str,
    name: str,
    slug: str,
    team_id: str,
    lead: str,
) -> dict:
    """Create a PM project via HITL API, return response dict."""
    resp = httpx.post(
        f"{hitl_url}/api/pm/projects",
        headers=auth_headers(token),
        json={
            "name": name,
            "slug": slug,
            "description": f"Auto-created by e2e test at {time.strftime('%Y-%m-%d %H:%M:%S')}",
            "lead": lead,
            "team_id": team_id,
        },
        timeout=10,
    )
    resp.raise_for_status()
    return resp.json()


def delete_pm_project(hitl_url: str, token: str, project_id: int) -> None:
    """Best-effort delete of a PM project."""
    try:
        httpx.delete(
            f"{hitl_url}/api/pm/projects/{project_id}",
            headers=auth_headers(token),
            timeout=10,
        )
    except Exception:
        pass


def cleanup_test_projects(hitl_url: str, token: str, slug_prefix: str) -> int:
    """Delete all PM projects whose slug starts with slug_prefix. Returns count."""
    deleted = 0
    try:
        resp = httpx.get(
            f"{hitl_url}/api/pm/projects",
            headers=auth_headers(token),
            timeout=10,
        )
        if resp.status_code == 200:
            for p in resp.json():
                if p.get("slug", "").startswith(slug_prefix):
                    delete_pm_project(hitl_url, token, p["id"])
                    deleted += 1
    except Exception:
        pass
    return deleted
