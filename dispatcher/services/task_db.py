"""Database operations for dispatcher tasks."""

from __future__ import annotations

import json
import os
from typing import Optional
from uuid import UUID, uuid4

import asyncpg

from core.config import settings
from models.task import Task, TaskPayload, TaskStatus
from models.schemas import RunTaskRequest


async def insert_task(pool: asyncpg.Pool, task: Task) -> None:
    """Insert the initial task row."""
    await pool.execute(
        """INSERT INTO project.dispatcher_tasks
            (id, agent_id, team_id, thread_id, project_slug, phase, iteration,
             instruction, context, previous_answers, docker_image, timeout_seconds)
           VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12)""",
        task.task_id,
        task.agent_id,
        task.team_id,
        task.thread_id,
        task.project_slug,
        task.phase,
        task.iteration,
        task.payload.instruction,
        json.dumps(task.payload.context, ensure_ascii=False, default=str),
        json.dumps(task.payload.previous_answers, ensure_ascii=False, default=str),
        task.docker_image or settings.agent_default_image,
        task.timeout_seconds,
    )


async def store_event(pool: asyncpg.Pool, task_id: UUID, event_type: str, data) -> None:
    """Insert an event row."""
    if isinstance(data, str):
        data_json = json.dumps(data)
    else:
        data_json = json.dumps(data, ensure_ascii=False, default=str)
    await pool.execute(
        """INSERT INTO project.dispatcher_task_events (task_id, event_type, data)
           VALUES ($1, $2, $3::jsonb)""",
        task_id,
        event_type,
        data_json,
    )


async def mark_status(
    pool: asyncpg.Pool, task_id: UUID, status: TaskStatus, error: Optional[str] = None
) -> None:
    """Update task status and completion time."""
    await pool.execute(
        """UPDATE project.dispatcher_tasks
           SET status = $1, completed_at = NOW(), error_message = $2
           WHERE id = $3""",
        status.value,
        error,
        task_id,
    )


async def fetch_task(pool: asyncpg.Pool, task_id: UUID) -> Optional[Task]:
    """Load a task from DB and return as a Task dataclass."""
    row = await pool.fetchrow(
        "SELECT * FROM project.dispatcher_tasks WHERE id = $1", task_id
    )
    if not row:
        return None
    return Task(
        task_id=row["id"],
        agent_id=row["agent_id"],
        team_id=row["team_id"],
        thread_id=row["thread_id"],
        project_slug=row["project_slug"],
        phase=row["phase"] or "build",
        iteration=row["iteration"] or 1,
        payload=TaskPayload(
            instruction=row["instruction"],
            context=json.loads(row["context"]) if row["context"] else {},
            previous_answers=json.loads(row["previous_answers"]) if row["previous_answers"] else [],
        ),
        timeout_seconds=row["timeout_seconds"] or 300,
        docker_image=row["docker_image"],
    )


def build_task(req: RunTaskRequest) -> Task:
    """Convert a request into a Task dataclass."""
    return Task(
        task_id=uuid4(),
        agent_id=req.agent_id,
        team_id=req.team_id,
        thread_id=req.thread_id,
        project_slug=req.project_slug,
        phase=req.phase,
        iteration=req.iteration,
        payload=TaskPayload(
            instruction=req.payload.instruction,
            context=req.payload.context,
            previous_answers=req.payload.previous_answers,
        ),
        timeout_seconds=req.timeout_seconds,
        docker_image=req.docker_image,
    )


def build_env(task: Task) -> dict[str, str]:
    """Build environment variables for the agent container."""
    return {
        "ANTHROPIC_API_KEY": os.environ.get("ANTHROPIC_API_KEY", ""),
        "AGENT_ROLE": task.agent_id,
        "AGENT_MAX_TURNS": os.environ.get("AGENT_MAX_TURNS", "10"),
        "AGENT_ALLOWED_TOOLS": os.environ.get(
            "AGENT_ALLOWED_TOOLS",
            "Read,Write,Edit,Bash(git *),Bash(pytest *)",
        ),
    }


def build_volumes(task: Task) -> list[str]:
    """Build volume bind mounts for the agent container."""
    slug = task.project_slug or "default"
    repo_path = f"{settings.ag_flow_root}/projects/{slug}/repo"
    return [f"{repo_path}:/workspace"]
