"""Task API routes."""

from __future__ import annotations

import json
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, HTTPException

from core.database import get_pool
from models.schemas import (
    RunTaskRequest,
    TaskArtifactResponse,
    TaskDetailResponse,
    TaskEventResponse,
    TaskResponse,
)

router = APIRouter(prefix="/tasks", tags=["tasks"])


def _get_runner():
    """Lazy import to avoid circular dependency at module load."""
    from main import get_task_runner
    return get_task_runner()


@router.post("/run", status_code=202)
async def run_task(req: RunTaskRequest, bg: BackgroundTasks) -> dict:
    """Launch a task in the background. Returns task_id immediately."""
    runner = _get_runner()
    task_id = await runner.create(req)
    bg.add_task(runner.execute_by_id, task_id)
    return {"task_id": str(task_id), "status": "pending"}


@router.get("/active")
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


@router.get("/{task_id}")
async def get_task(task_id: UUID) -> TaskDetailResponse:
    """Get task detail with events and artifacts."""
    pool = get_pool()
    row = await pool.fetchrow(
        "SELECT * FROM project.dispatcher_tasks WHERE id = $1", task_id
    )
    if not row:
        raise HTTPException(404, "Task not found")

    events = await pool.fetch(
        """SELECT id, task_id, event_type, data, created_at
           FROM project.dispatcher_task_events
           WHERE task_id = $1 ORDER BY created_at""",
        task_id,
    )
    artifacts = await pool.fetch(
        """SELECT id, task_id, key, deliverable_type, file_path, git_branch,
                  category, status, created_at
           FROM project.dispatcher_task_artifacts
           WHERE task_id = $1 ORDER BY created_at""",
        task_id,
    )

    return TaskDetailResponse(
        task_id=row["id"],
        status=row["status"],
        agent_id=row["agent_id"],
        team_id=row["team_id"],
        project_slug=row["project_slug"],
        phase=row["phase"],
        cost_usd=float(row["cost_usd"] or 0),
        created_at=row["created_at"],
        started_at=row["started_at"],
        completed_at=row["completed_at"],
        error_message=row["error_message"],
        events=[
            TaskEventResponse(
                id=e["id"],
                task_id=e["task_id"],
                event_type=e["event_type"],
                data=e["data"],
                created_at=e["created_at"],
            )
            for e in events
        ],
        artifacts=[
            TaskArtifactResponse(
                id=a["id"],
                task_id=a["task_id"],
                key=a["key"],
                deliverable_type=a["deliverable_type"],
                file_path=a["file_path"],
                git_branch=a["git_branch"],
                category=a["category"],
                status=a["status"],
                created_at=a["created_at"],
            )
            for a in artifacts
        ],
    )


@router.get("/{task_id}/events")
async def get_task_events(task_id: UUID) -> list[TaskEventResponse]:
    """Get events for a task."""
    pool = get_pool()
    events = await pool.fetch(
        """SELECT id, task_id, event_type, data, created_at
           FROM project.dispatcher_task_events
           WHERE task_id = $1 ORDER BY created_at""",
        task_id,
    )
    return [
        TaskEventResponse(
            id=e["id"],
            task_id=e["task_id"],
            event_type=e["event_type"],
            data=e["data"],
            created_at=e["created_at"],
        )
        for e in events
    ]


@router.post("/{task_id}/cancel")
async def cancel_task(task_id: UUID) -> dict:
    """Cancel a running task."""
    runner = _get_runner()
    ok = await runner.cancel(task_id)
    if not ok:
        raise HTTPException(400, "Task not cancellable")
    return {"status": "cancelled"}
