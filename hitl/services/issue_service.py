"""Issue management service — CRUD, bulk, search, blocking logic."""

from __future__ import annotations

from typing import Optional

import structlog

from core.database import execute, fetch_all, fetch_one, get_pool
from schemas.issue import IssueCreate, IssueDetail, IssueResponse, IssueUpdate
from services.issue_helpers import (
    check_unblock_cascade,
    fetch_issue_response,
    log_activity,
    notify_on_update,
    row_to_response,
)

log = structlog.get_logger(__name__)

VALID_STATUSES = {"backlog", "todo", "in-progress", "in-review", "done"}


def _get_team_prefix(team_id: str) -> str:
    """Return a 3-4 char uppercase prefix from team_id."""
    clean = team_id.replace("-", "").replace("_", "")
    return clean[:4].upper() if len(clean) >= 4 else clean.upper()


async def _next_issue_id(team_id: str) -> str:
    """Atomically allocate the next issue ID for a team."""
    pool = get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            row = await conn.fetchrow(
                "SELECT next_seq FROM project.pm_issue_counters "
                "WHERE team_id = $1 FOR UPDATE",
                team_id,
            )
            if row is None:
                await conn.execute(
                    "INSERT INTO project.pm_issue_counters (team_id, next_seq) "
                    "VALUES ($1, 2)",
                    team_id,
                )
                seq = 1
            else:
                seq = row["next_seq"]
                await conn.execute(
                    "UPDATE project.pm_issue_counters "
                    "SET next_seq = next_seq + 1 WHERE team_id = $1",
                    team_id,
                )
    prefix = _get_team_prefix(team_id)
    return f"{prefix}-{seq:03d}"


async def list_issues(
    team_id: Optional[str] = None,
    project_id: Optional[int] = None,
    status: Optional[str] = None,
    assignee: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
) -> list[IssueResponse]:
    """List issues with optional filters, including blocking metadata."""
    query = """
        SELECT i.*,
            EXISTS(
                SELECT 1 FROM project.pm_issue_relations r
                JOIN project.pm_issues blocker ON r.source_issue_id = blocker.id
                WHERE r.target_issue_id = i.id
                  AND r.type = 'blocks'
                  AND blocker.status != 'done'
            ) AS is_blocked,
            (SELECT COUNT(*) FROM project.pm_issue_relations
             WHERE source_issue_id = i.id AND type = 'blocks') AS blocking_count,
            (SELECT COUNT(*) FROM project.pm_issue_relations
             WHERE target_issue_id = i.id AND type = 'blocks') AS blocked_by_count
        FROM project.pm_issues i
        WHERE 1=1
    """
    args: list = []
    idx = 1

    if team_id is not None:
        query += f" AND i.team_id = ${idx}"
        args.append(team_id)
        idx += 1
    if project_id is not None:
        query += f" AND i.project_id = ${idx}"
        args.append(project_id)
        idx += 1
    if status is not None:
        query += f" AND i.status = ${idx}"
        args.append(status)
        idx += 1
    if assignee is not None:
        query += f" AND i.assignee = ${idx}"
        args.append(assignee)
        idx += 1

    query += f" ORDER BY i.created_at DESC LIMIT ${idx} OFFSET ${idx + 1}"
    args.extend([limit, offset])

    rows = await fetch_all(query, *args)
    return [row_to_response(r) for r in rows]


async def get_issue(issue_id: str) -> Optional[IssueDetail]:
    """Get a single issue with relations and project name."""
    row = await fetch_one(
        """
        SELECT i.*,
            EXISTS(
                SELECT 1 FROM project.pm_issue_relations r
                JOIN project.pm_issues blocker ON r.source_issue_id = blocker.id
                WHERE r.target_issue_id = i.id
                  AND r.type = 'blocks'
                  AND blocker.status != 'done'
            ) AS is_blocked,
            (SELECT COUNT(*) FROM project.pm_issue_relations
             WHERE source_issue_id = i.id AND type = 'blocks') AS blocking_count,
            (SELECT COUNT(*) FROM project.pm_issue_relations
             WHERE target_issue_id = i.id AND type = 'blocks') AS blocked_by_count,
            p.name AS project_name
        FROM project.pm_issues i
        LEFT JOIN project.pm_projects p ON i.project_id = p.id
        WHERE i.id = $1
        """,
        issue_id,
    )
    if row is None:
        return None

    from services.relation_service import list_relations

    relations = await list_relations(issue_id)
    resp = row_to_response(row)
    return IssueDetail(
        **resp.model_dump(),
        relations=relations,
        project_name=row["project_name"],
    )


async def create_issue(
    data: IssueCreate,
    team_id: str,
    user_email: str,
) -> IssueResponse:
    """Create a new issue with auto-generated ID."""
    issue_id = await _next_issue_id(team_id)

    row = await fetch_one(
        """
        INSERT INTO project.pm_issues
            (id, project_id, title, description, status, priority,
             assignee, team_id, tags, phase, created_by)
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
        RETURNING *,
            FALSE AS is_blocked,
            0::bigint AS blocking_count,
            0::bigint AS blocked_by_count
        """,
        issue_id,
        data.project_id,
        data.title,
        data.description,
        data.status,
        data.priority,
        data.assignee,
        team_id,
        data.tags,
        data.phase,
        user_email,
    )

    if data.project_id:
        await log_activity(data.project_id, user_email, "issue_created", issue_id, data.title)

    if data.assignee and data.assignee != user_email:
        from services.inbox_service import create_notification

        text = f"{user_email} assigned {issue_id} to you"
        await create_notification(data.assignee, "assign", text, issue_id=issue_id)

    log.info("issue_created", issue_id=issue_id, team_id=team_id)
    return row_to_response(row)


async def update_issue(
    issue_id: str,
    data: IssueUpdate,
    user_email: str,
) -> Optional[IssueResponse]:
    """Update an issue, log changes, and send notifications."""
    current = await fetch_one(
        "SELECT * FROM project.pm_issues WHERE id = $1", issue_id,
    )
    if current is None:
        return None

    fields = data.model_dump(exclude_none=True)
    if not fields:
        return await fetch_issue_response(issue_id)

    sets: list[str] = []
    args: list = []
    idx = 1
    for key, value in fields.items():
        sets.append(f"{key} = ${idx}")
        args.append(value)
        idx += 1

    sets.append("updated_at = NOW()")
    args.append(issue_id)

    query = (
        f"UPDATE project.pm_issues SET {', '.join(sets)} "
        f"WHERE id = ${idx}"
    )
    await execute(query, *args)

    project_id = current["project_id"]
    if project_id:
        for key, value in fields.items():
            old_val = current[key]
            if old_val != value:
                detail = f"{key}: {old_val} -> {value}"
                await log_activity(project_id, user_email, f"issue_{key}_changed", issue_id, detail)

    await notify_on_update(current, fields, issue_id, user_email)

    if fields.get("status") == "done":
        await check_unblock_cascade(issue_id, user_email)

    return await fetch_issue_response(issue_id)


async def delete_issue(issue_id: str, user_email: str) -> bool:
    """Delete an issue and log the activity."""
    current = await fetch_one(
        "SELECT project_id, title FROM project.pm_issues WHERE id = $1",
        issue_id,
    )
    if current is None:
        return False

    await execute("DELETE FROM project.pm_issues WHERE id = $1", issue_id)

    if current["project_id"]:
        await log_activity(
            current["project_id"], user_email, "issue_deleted",
            issue_id, current["title"],
        )
    log.info("issue_deleted", issue_id=issue_id)
    return True


async def bulk_create(
    issues: list[IssueCreate],
    project_id: int,
    team_id: str,
    user_email: str,
) -> list[IssueResponse]:
    """Create multiple issues at once."""
    results: list[IssueResponse] = []
    for issue_data in issues:
        issue_data.project_id = project_id
        resp = await create_issue(issue_data, team_id, user_email)
        results.append(resp)
    return results


async def search_issues(
    team_id: str,
    query: str,
    limit: int = 50,
) -> list[IssueResponse]:
    """Search issues by ID or title."""
    pattern = f"%{query}%"
    rows = await fetch_all(
        """
        SELECT i.*,
            FALSE AS is_blocked,
            0::bigint AS blocking_count,
            0::bigint AS blocked_by_count
        FROM project.pm_issues i
        WHERE i.team_id = $1
          AND (i.id ILIKE $2 OR i.title ILIKE $2)
        ORDER BY i.created_at DESC
        LIMIT $3
        """,
        team_id, pattern, limit,
    )
    return [row_to_response(r) for r in rows]
