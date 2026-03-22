"""Internal endpoints for monitoring and cost tracking."""

from __future__ import annotations

from fastapi import APIRouter

from core.database import get_pool
from models.schemas import ProjectCostsResponse, CostSummaryResponse, TaskResponse

router = APIRouter(tags=["internal"])


@router.get("/costs/{project_slug}")
async def get_project_costs(project_slug: str) -> ProjectCostsResponse:
    """Get cost summary for a project."""
    pool = get_pool()
    rows = await pool.fetch(
        """SELECT project_slug, team_id, phase, agent_id,
                  total_cost_usd, task_count, avg_cost_per_task
           FROM project.dispatcher_cost_summary
           WHERE project_slug = $1
           ORDER BY phase, agent_id""",
        project_slug,
    )
    by_phase = [
        CostSummaryResponse(
            project_slug=r["project_slug"],
            team_id=r["team_id"],
            phase=r["phase"],
            agent_id=r["agent_id"],
            total_cost_usd=float(r["total_cost_usd"]),
            task_count=r["task_count"],
            avg_cost_per_task=float(r["avg_cost_per_task"]),
        )
        for r in rows
    ]
    total = sum(r.total_cost_usd for r in by_phase)
    return ProjectCostsResponse(
        project_slug=project_slug,
        total_cost_usd=total,
        by_phase=by_phase,
    )


@router.get("/tasks/active")
async def get_active_tasks() -> list[TaskResponse]:
    """Get currently running or waiting tasks."""
    pool = get_pool()
    rows = await pool.fetch(
        """SELECT id, status, agent_id, team_id, project_slug, phase,
                  cost_usd, created_at, started_at, completed_at, error_message
           FROM project.dispatcher_tasks
           WHERE status IN ('running', 'waiting_hitl', 'pending')
           ORDER BY created_at DESC
           LIMIT 50"""
    )
    return [
        TaskResponse(
            task_id=r["id"],
            status=r["status"],
            agent_id=r["agent_id"],
            team_id=r["team_id"],
            project_slug=r["project_slug"],
            phase=r["phase"],
            cost_usd=float(r["cost_usd"] or 0),
            created_at=r["created_at"],
            started_at=r["started_at"],
            completed_at=r["completed_at"],
            error_message=r["error_message"],
        )
        for r in rows
    ]
