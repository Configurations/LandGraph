"""Activity timeline service — log, list, merge PM + agent entries."""

from __future__ import annotations

from typing import Optional

import structlog

from core.database import execute, fetch_all, fetch_one
from schemas.inbox import ActivityEntry

log = structlog.get_logger(__name__)


async def log_activity(
    project_id: int,
    user_name: str,
    action: str,
    issue_id: Optional[str] = None,
    detail: Optional[str] = None,
) -> None:
    """Insert a row into pm_activity."""
    await execute(
        """
        INSERT INTO project.pm_activity (project_id, user_name, action, issue_id, detail)
        VALUES ($1, $2, $3, $4, $5)
        """,
        project_id, user_name, action, issue_id, detail,
    )


async def list_activity(
    project_id: int,
    limit: int = 50,
    offset: int = 0,
) -> list[ActivityEntry]:
    """List PM activity for a project, newest first."""
    rows = await fetch_all(
        """
        SELECT id, project_id, user_name, action, issue_id, detail, created_at
        FROM project.pm_activity
        WHERE project_id = $1
        ORDER BY created_at DESC
        LIMIT $2 OFFSET $3
        """,
        project_id, limit, offset,
    )
    return [_pm_row_to_entry(r) for r in rows]


async def get_merged_activity(
    project_id: int,
    team_id: str,
    limit: int = 50,
) -> list[ActivityEntry]:
    """Merge PM activity and agent task events, sorted by time desc."""
    # PM entries
    pm_rows = await fetch_all(
        """
        SELECT id, project_id, user_name, action, issue_id, detail, created_at
        FROM project.pm_activity
        WHERE project_id = $1
        ORDER BY created_at DESC
        LIMIT $2
        """,
        project_id, limit,
    )
    pm_entries = [_pm_row_to_entry(r) for r in pm_rows]

    # Agent entries from dispatcher tasks + events
    slug_row = await fetch_one(
        "SELECT slug FROM project.pm_projects WHERE id = $1", project_id,
    )
    agent_entries: list[ActivityEntry] = []
    if slug_row and slug_row["slug"]:
        slug = slug_row["slug"]
        agent_rows = await fetch_all(
            """
            SELECT e.id, e.event_type AS action,
                   t.agent_id AS user_name,
                   e.detail, e.created_at
            FROM project.dispatcher_task_events e
            JOIN project.dispatcher_tasks t ON e.task_id = t.id
            WHERE t.project_slug = $1
            ORDER BY e.created_at DESC
            LIMIT $2
            """,
            slug, limit,
        )
        for r in agent_rows:
            detail_text = r["detail"]
            if isinstance(detail_text, dict):
                detail_text = str(detail_text)
            agent_entries.append(ActivityEntry(
                id=r["id"],
                project_id=project_id,
                user_name=r["user_name"] or "agent",
                action=r["action"] or "task_event",
                issue_id=None,
                detail=detail_text,
                created_at=r["created_at"],
                source="agent",
            ))

    # Merge and sort
    merged = pm_entries + agent_entries
    merged.sort(key=lambda e: e.created_at, reverse=True)
    return merged[:limit]


def _pm_row_to_entry(row: dict) -> ActivityEntry:
    """Map a pm_activity row to ActivityEntry."""
    return ActivityEntry(
        id=row["id"],
        project_id=row["project_id"],
        user_name=row["user_name"],
        action=row["action"],
        issue_id=row["issue_id"],
        detail=row["detail"],
        created_at=row["created_at"],
        source="pm",
    )
