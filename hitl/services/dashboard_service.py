"""Dashboard service — active tasks, costs, overview."""

from __future__ import annotations

from typing import Optional

import httpx
import structlog

from core.config import settings
from core.database import fetch_all, fetch_one

log = structlog.get_logger(__name__)

_HTTP_TIMEOUT = 10.0


async def get_active_tasks(team_id: Optional[str] = None) -> list[dict]:
    """Fetch active tasks from the dispatcher API."""
    url = settings.dispatcher_url
    if not url:
        return []

    try:
        async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
            resp = await client.get(f"{url.rstrip('/')}/api/tasks/active")
            resp.raise_for_status()
            tasks = resp.json()
    except Exception as exc:
        log.warning("dashboard_active_tasks_error", error=str(exc))
        return []

    if team_id:
        tasks = [t for t in tasks if t.get("team_id") == team_id]
    return tasks


async def get_project_costs(slug: str) -> Optional[dict]:
    """Fetch cost breakdown for a project from the dispatcher API."""
    url = settings.dispatcher_url
    if not url:
        return None

    try:
        async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
            resp = await client.get(f"{url.rstrip('/')}/api/costs/{slug}")
            resp.raise_for_status()
            return resp.json()
    except Exception as exc:
        log.warning("dashboard_costs_error", slug=slug, error=str(exc))
        return None


async def get_overview(
    team_id: Optional[str],
    user_teams: list[str],
) -> dict:
    """Aggregate overview metrics for the dashboard."""
    if not user_teams:
        return {"pending_questions": 0, "active_tasks": 0, "total_cost": 0.0}

    # Pending HITL questions
    placeholders = ", ".join(f"${i + 1}" for i in range(len(user_teams)))
    q_count = f"""
        SELECT COUNT(*) AS cnt
        FROM project.hitl_requests
        WHERE status = 'pending' AND team_id IN ({placeholders})
    """
    row = await fetch_one(q_count, *user_teams)
    pending = row["cnt"] if row else 0

    # Active tasks
    tasks = await get_active_tasks(team_id)
    active_count = len(tasks)

    # Total cost across user teams
    cost_q = f"""
        SELECT COALESCE(SUM(cost_usd), 0) AS total
        FROM project.dispatcher_tasks
        WHERE team_id IN ({placeholders})
    """
    cost_row = await fetch_one(cost_q, *user_teams)
    total_cost = float(cost_row["total"]) if cost_row else 0.0

    return {
        "pending_questions": pending,
        "active_tasks": active_count,
        "total_cost": total_cost,
    }
