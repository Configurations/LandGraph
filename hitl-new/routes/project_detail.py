"""Project detail routes — overview and team endpoints."""

from __future__ import annotations

from typing import Any, Optional

import structlog
from fastapi import APIRouter, Depends, HTTPException

from core.database import fetch_all, fetch_one
from core.security import TokenData, get_current_user
from services.dashboard_service import get_project_costs

log = structlog.get_logger(__name__)

router = APIRouter(prefix="/api/projects", tags=["project-detail"])


@router.get("/{slug}/overview")
async def get_project_overview(
    slug: str,
    user: TokenData = Depends(get_current_user),
) -> dict[str, Any]:
    """Get overview metrics for a project."""
    proj = await fetch_one(
        "SELECT id, team_id, status FROM project.pm_projects WHERE slug = $1",
        slug,
    )
    if proj is None:
        raise HTTPException(status_code=404, detail="project.not_found")

    project_id = proj["id"]

    # Issue counts by status
    issue_rows = await fetch_all(
        """
        SELECT status, COUNT(*) AS cnt
        FROM project.pm_issues
        WHERE project_id = $1
        GROUP BY status
        """,
        project_id,
    )
    issue_counts: dict[str, int] = {r["status"]: r["cnt"] for r in issue_rows}
    total_issues = sum(issue_counts.values())

    # Deliverable counts by status
    deliv_rows = await fetch_all(
        """
        SELECT a.status, COUNT(*) AS cnt
        FROM project.dispatcher_task_artifacts a
        JOIN project.dispatcher_tasks t ON a.task_id = t.id
        WHERE t.project_slug = $1
        GROUP BY a.status
        """,
        slug,
    )
    deliv_counts: dict[str, int] = {r["status"]: r["cnt"] for r in deliv_rows}
    total_deliverables = sum(deliv_counts.values())

    # Costs
    costs = await get_project_costs(slug)

    # Current phase
    phase_row = await fetch_one(
        """
        SELECT phase FROM project.dispatcher_tasks
        WHERE project_slug = $1 AND status IN ('running', 'waiting_hitl', 'pending')
        ORDER BY created_at DESC LIMIT 1
        """,
        slug,
    )
    current_phase = phase_row["phase"] if phase_row else None

    return {
        "project_id": project_id,
        "status": proj["status"],
        "current_phase": current_phase,
        "issues": {"total": total_issues, "by_status": issue_counts},
        "deliverables": {"total": total_deliverables, "by_status": deliv_counts},
        "costs": costs,
    }


@router.get("/{slug}/team")
async def get_project_team(
    slug: str,
    user: TokenData = Depends(get_current_user),
) -> dict[str, Any]:
    """Get team members and agents with stats for a project."""
    proj = await fetch_one(
        "SELECT id, team_id FROM project.pm_projects WHERE slug = $1",
        slug,
    )
    if proj is None:
        raise HTTPException(status_code=404, detail="project.not_found")

    project_id = proj["id"]

    # Human members
    members = await fetch_all(
        """
        SELECT pm.user_name, pm.role,
               COUNT(i.id) FILTER (WHERE i.status != 'done') AS active_issues,
               COUNT(i.id) FILTER (WHERE i.status = 'done') AS completed_issues
        FROM project.pm_project_members pm
        LEFT JOIN project.pm_issues i ON i.assignee = pm.user_name AND i.project_id = $1
        WHERE pm.project_id = $1
        GROUP BY pm.user_name, pm.role
        """,
        project_id,
    )

    # Agent tasks
    agents = await fetch_all(
        """
        SELECT agent_id,
               COUNT(*) AS total_tasks,
               COUNT(*) FILTER (WHERE status = 'success') AS completed,
               COUNT(*) FILTER (WHERE status IN ('running', 'waiting_hitl')) AS active,
               COALESCE(SUM(cost_usd), 0) AS cost
        FROM project.dispatcher_tasks
        WHERE project_slug = $1
        GROUP BY agent_id
        """,
        slug,
    )

    return {
        "members": [
            {
                "name": m["user_name"],
                "role": m["role"],
                "active_issues": m["active_issues"],
                "completed_issues": m["completed_issues"],
            }
            for m in members
        ],
        "agents": [
            {
                "agent_id": a["agent_id"],
                "total_tasks": a["total_tasks"],
                "completed": a["completed"],
                "active": a["active"],
                "cost": float(a["cost"]),
            }
            for a in agents
        ],
    }
