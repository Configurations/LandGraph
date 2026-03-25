"""Project detail routes — overview and team endpoints."""

from __future__ import annotations

from typing import Any, Optional

import structlog
from fastapi import APIRouter, Depends, HTTPException

from core.database import fetch_all, fetch_one
from core.security import TokenData, get_current_user
from services.dashboard_service import get_project_costs
from services.avatar_resolver import resolve_agent_avatar
from schemas.chat import AgentResponse

log = structlog.get_logger(__name__)

router = APIRouter(prefix="/api/projects", tags=["project-detail"])


@router.get("/{slug}/overview")
async def get_project_overview(
    slug: str,
    user: TokenData = Depends(get_current_user),
) -> dict[str, Any]:
    """Get overview metrics for a project."""
    proj = await fetch_one(
        "SELECT id, team_id, status, lead, created_at FROM project.pm_projects WHERE slug = $1",
        slug,
    )
    if proj is None:
        raise HTTPException(status_code=404, detail="project.not_found")

    project_id = proj["id"]

    # Members
    member_rows = await fetch_all(
        "SELECT user_name FROM project.pm_project_members WHERE project_id = $1",
        project_id,
    )
    members = [r["user_name"] for r in member_rows]

    # Issue counts by status — ensure all 5 statuses present
    issue_rows = await fetch_all(
        """
        SELECT status, COUNT(*) AS cnt
        FROM project.pm_issues
        WHERE project_id = $1
        GROUP BY status
        """,
        project_id,
    )
    issues_by_status: dict[str, int] = {
        s: 0 for s in ("backlog", "todo", "in-progress", "in-review", "done")
    }
    for r in issue_rows:
        issues_by_status[r["status"]] = r["cnt"]

    # Deliverable counts
    deliv_rows = await fetch_all(
        """
        SELECT COUNT(*) AS cnt
        FROM project.dispatcher_task_artifacts a
        JOIN project.dispatcher_tasks t ON a.task_id = t.id
        WHERE t.project_slug = $1
        """,
        slug,
    )
    total_deliverables = deliv_rows[0]["cnt"] if deliv_rows else 0

    # Costs
    costs = await get_project_costs(slug)
    total_cost = costs.get("total", 0.0) if costs and isinstance(costs, dict) else 0.0

    # Current phase
    phase_row = await fetch_one(
        """
        SELECT phase FROM project.dispatcher_tasks
        WHERE project_slug = $1 AND status IN ('running', 'waiting_hitl', 'pending')
        ORDER BY created_at DESC LIMIT 1
        """,
        slug,
    )
    current_phase = phase_row["phase"] if phase_row else ""

    # Start date from project creation
    start_date = ""
    if proj["created_at"]:
        ts = proj["created_at"]
        start_date = ts.isoformat() if hasattr(ts, "isoformat") else str(ts)

    return {
        "health": "on-track",
        "lead": proj["lead"] or "",
        "start_date": start_date,
        "end_date": None,
        "members": members,
        "total_cost": float(total_cost),
        "issues_by_status": issues_by_status,
        "deliverables_count": total_deliverables,
        "current_phase": current_phase,
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


@router.get("/{slug}/agents", response_model=list[AgentResponse])
async def get_project_agents(
    slug: str,
    user: TokenData = Depends(get_current_user),
) -> list[AgentResponse]:
    """Get agents for a project's team (from agents_registry.json)."""
    import json
    import os

    proj = await fetch_one(
        "SELECT id, team_id FROM project.pm_projects WHERE slug = $1", slug,
    )
    if proj is None:
        raise HTTPException(status_code=404, detail="project.not_found")

    team_id = proj["team_id"]
    if not team_id:
        return []

    # Load agents from registry (same logic as routes/agents.py)
    from core.config import _find_config_dir, load_teams
    teams = load_teams()
    team_dir = ""
    for t in teams:
        if t["id"] == team_id:
            team_dir = t.get("directory", "")
            break
    if not team_dir:
        return []

    config_dir = _find_config_dir()
    reg_path = os.path.join(config_dir, "Teams", team_dir, "agents_registry.json")
    if not os.path.isfile(reg_path):
        reg_path = os.path.join(config_dir, team_dir, "agents_registry.json")
    if not os.path.isfile(reg_path):
        return []

    try:
        with open(reg_path, encoding="utf-8") as f:
            registry = json.load(f)
    except (OSError, json.JSONDecodeError):
        return []

    result = []
    for agent_id, agent_cfg in registry.get("agents", {}).items():
        row = await fetch_one(
            "SELECT COUNT(*) AS cnt FROM project.hitl_requests WHERE agent_id = $1 AND team_id = $2 AND status = 'pending'",
            agent_id, team_id,
        )
        pending = row["cnt"] if row else 0
        result.append(AgentResponse(
            id=agent_id,
            name=agent_cfg.get("name", agent_id),
            llm=agent_cfg.get("llm", ""),
            type=agent_cfg.get("type", "single"),
            pending_questions=pending,
            avatar_url=resolve_agent_avatar(team_id, agent_id),
        ))
    return result


@router.get("/{slug}/relations")
async def get_project_relations(
    slug: str,
    user: TokenData = Depends(get_current_user),
) -> list[dict]:
    """Get issue relations for a project (for dependency graph)."""
    proj = await fetch_one(
        "SELECT id FROM project.pm_projects WHERE slug = $1", slug,
    )
    if proj is None:
        raise HTTPException(status_code=404, detail="project.not_found")

    rows = await fetch_all(
        """
        SELECT r.source_issue_id AS "sourceId",
               r.target_issue_id AS "targetId",
               r.type
        FROM project.pm_issue_relations r
        JOIN project.pm_issues i ON r.source_issue_id = i.id
        WHERE i.project_id = $1
        """,
        proj["id"],
    )
    return [dict(r) for r in rows]
