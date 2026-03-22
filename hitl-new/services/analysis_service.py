"""Analysis service — dispatch AI analysis tasks and track conversations."""

from __future__ import annotations

from typing import Any, Optional

import httpx
import structlog

from core.config import settings
from core.database import execute, fetch_all, fetch_one
from schemas.rag import ConversationMessage

log = structlog.get_logger(__name__)


async def start_analysis(project_slug: str, team_id: str) -> dict[str, Any]:
    """Dispatch an analysis task to the dispatcher service."""
    url = f"{settings.dispatcher_url}/api/tasks/run"
    rag_endpoint = f"http://langgraph-hitl:8090/api/internal/rag/search"

    payload = {
        "agent_id": "project_analyst",
        "team_id": team_id,
        "thread_id": f"analysis-{project_slug}",
        "project_slug": project_slug,
        "phase": "analysis",
        "payload": {
            "instruction": "Analyse les documents du projet et produis un rapport.",
            "context": {
                "rag_endpoint": rag_endpoint,
                "project_slug": project_slug,
            },
        },
    }

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(url, json=payload)
            resp.raise_for_status()
            data = resp.json()
    except httpx.HTTPError as exc:
        log.error("analysis_dispatch_failed", slug=project_slug, error=str(exc))
        return {"error": "dispatcher_unavailable"}

    task_id = data.get("task_id", data.get("id", ""))
    log.info("analysis_started", slug=project_slug, task_id=task_id)
    return {"task_id": task_id}


async def get_analysis_status(task_id: str) -> dict[str, Any]:
    """Check the status of a running analysis task."""
    url = f"{settings.dispatcher_url}/api/tasks/{task_id}"

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            return resp.json()
    except httpx.HTTPError as exc:
        log.error("analysis_status_failed", task_id=task_id, error=str(exc))
        return {"status": "unavailable"}


async def save_message(
    project_slug: str,
    sender: str,
    content: str,
    task_id: Optional[str] = None,
) -> None:
    """Save a conversation message to the database."""
    await execute(
        """INSERT INTO project.rag_conversations
           (project_slug, task_id, sender, content)
           VALUES ($1, $2, $3, $4)""",
        project_slug,
        task_id,
        sender,
        content,
    )


async def get_conversation(project_slug: str) -> list[ConversationMessage]:
    """Retrieve the full conversation history for a project."""
    rows = await fetch_all(
        """SELECT id, project_slug, task_id, sender, content, created_at
           FROM project.rag_conversations
           WHERE project_slug = $1
           ORDER BY created_at ASC""",
        project_slug,
    )
    return [
        ConversationMessage(
            id=r["id"],
            project_slug=r["project_slug"],
            task_id=r["task_id"],
            sender=r["sender"],
            content=r["content"],
            created_at=r["created_at"],
        )
        for r in rows
    ]
