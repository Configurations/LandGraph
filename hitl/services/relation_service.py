"""Issue relation service — CRUD and inverse-type mapping."""

from __future__ import annotations

from typing import Optional

import structlog

from core.database import execute, fetch_all, fetch_one
from schemas.issue import RelationResponse
from schemas.relation import RelationCreate

log = structlog.get_logger(__name__)

INVERSE_TYPES: dict[str, dict[str, str]] = {
    "blocks": {"outgoing": "Blocks", "incoming": "Blocked by"},
    "relates-to": {"outgoing": "Relates to", "incoming": "Relates to"},
    "parent": {"outgoing": "Parent of", "incoming": "Sub-task of"},
    "duplicates": {"outgoing": "Duplicates", "incoming": "Duplicated by"},
}


async def list_relations(issue_id: str) -> list[RelationResponse]:
    """List all relations (outgoing + incoming) for an issue."""
    outgoing = await fetch_all(
        """
        SELECT r.id, r.type, r.target_issue_id AS issue_id,
               r.reason, r.created_by, r.created_at,
               i.title AS issue_title, i.status AS issue_status
        FROM project.pm_issue_relations r
        JOIN project.pm_issues i ON r.target_issue_id = i.id
        WHERE r.source_issue_id = $1
        """,
        issue_id,
    )
    incoming = await fetch_all(
        """
        SELECT r.id, r.type, r.source_issue_id AS issue_id,
               r.reason, r.created_by, r.created_at,
               i.title AS issue_title, i.status AS issue_status
        FROM project.pm_issue_relations r
        JOIN project.pm_issues i ON r.source_issue_id = i.id
        WHERE r.target_issue_id = $1
        """,
        issue_id,
    )

    results: list[RelationResponse] = []
    for r in outgoing:
        inv = INVERSE_TYPES.get(r["type"], {})
        results.append(RelationResponse(
            id=r["id"],
            type=r["type"],
            direction="outgoing",
            display_type=inv.get("outgoing", r["type"]),
            issue_id=r["issue_id"],
            issue_title=r["issue_title"] or "",
            issue_status=r["issue_status"] or "",
            reason=r["reason"] or "",
            created_by=r["created_by"],
            created_at=r["created_at"],
        ))
    for r in incoming:
        inv = INVERSE_TYPES.get(r["type"], {})
        results.append(RelationResponse(
            id=r["id"],
            type=r["type"],
            direction="incoming",
            display_type=inv.get("incoming", r["type"]),
            issue_id=r["issue_id"],
            issue_title=r["issue_title"] or "",
            issue_status=r["issue_status"] or "",
            reason=r["reason"] or "",
            created_by=r["created_by"],
            created_at=r["created_at"],
        ))
    return results


async def create_relation(
    source_id: str,
    data: RelationCreate,
    user_email: str,
) -> RelationResponse:
    """Create a relation between two issues."""
    if source_id == data.target_issue_id:
        raise ValueError("issue.self_relation")

    row = await fetch_one(
        """
        INSERT INTO project.pm_issue_relations
            (type, source_issue_id, target_issue_id, reason, created_by)
        VALUES ($1, $2, $3, $4, $5)
        RETURNING id, type, target_issue_id AS issue_id,
                  reason, created_by, created_at
        """,
        data.type, source_id, data.target_issue_id, data.reason, user_email,
    )

    # Fetch target info
    target = await fetch_one(
        "SELECT title, status FROM project.pm_issues WHERE id = $1",
        data.target_issue_id,
    )
    title = target["title"] if target else ""
    status = target["status"] if target else ""

    inv = INVERSE_TYPES.get(data.type, {})

    # If type is 'blocks', notify target assignee
    if data.type == "blocks":
        target_issue = await fetch_one(
            "SELECT assignee FROM project.pm_issues WHERE id = $1",
            data.target_issue_id,
        )
        if target_issue and target_issue["assignee"]:
            from services.inbox_service import create_notification

            text = f"{source_id} now blocks {data.target_issue_id}"
            await create_notification(
                target_issue["assignee"], "blocked", text,
                issue_id=data.target_issue_id,
                related_issue_id=source_id,
                relation_type="blocks",
            )

    # Log activity for source issue
    source_issue = await fetch_one(
        "SELECT project_id FROM project.pm_issues WHERE id = $1", source_id,
    )
    if source_issue and source_issue["project_id"]:
        await execute(
            """
            INSERT INTO project.pm_activity
                (project_id, user_name, action, issue_id, detail)
            VALUES ($1, $2, $3, $4, $5)
            """,
            source_issue["project_id"],
            user_email,
            "relation_created",
            source_id,
            f"{data.type} -> {data.target_issue_id}",
        )

    log.info("relation_created", source=source_id, target=data.target_issue_id, type=data.type)
    return RelationResponse(
        id=row["id"],
        type=row["type"],
        direction="outgoing",
        display_type=inv.get("outgoing", data.type),
        issue_id=data.target_issue_id,
        issue_title=title,
        issue_status=status,
        reason=data.reason,
        created_by=user_email,
        created_at=row["created_at"],
    )


async def delete_relation(relation_id: int, user_email: str) -> bool:
    """Delete a relation and notify if it was a blocking relation."""
    rel = await fetch_one(
        """
        SELECT id, type, source_issue_id, target_issue_id
        FROM project.pm_issue_relations WHERE id = $1
        """,
        relation_id,
    )
    if rel is None:
        return False

    await execute("DELETE FROM project.pm_issue_relations WHERE id = $1", relation_id)

    # If it was a 'blocks' relation, check if target is now unblocked
    if rel["type"] == "blocks":
        target_id = rel["target_issue_id"]
        still_blocked = await fetch_one(
            """
            SELECT 1 FROM project.pm_issue_relations r
            JOIN project.pm_issues blocker ON r.source_issue_id = blocker.id
            WHERE r.target_issue_id = $1
              AND r.type = 'blocks'
              AND blocker.status != 'done'
            """,
            target_id,
        )
        if still_blocked is None:
            target_issue = await fetch_one(
                "SELECT assignee FROM project.pm_issues WHERE id = $1",
                target_id,
            )
            if target_issue and target_issue["assignee"]:
                from services.inbox_service import create_notification

                source_id = rel["source_issue_id"]
                text = f"Blocker {source_id} removed — {target_id} is now unblocked"
                await create_notification(
                    target_issue["assignee"], "unblocked", text,
                    issue_id=target_id, related_issue_id=source_id,
                )

    log.info("relation_deleted", relation_id=relation_id)
    return True


async def bulk_create(
    source_id: str,
    relations: list[RelationCreate],
    user_email: str,
) -> list[RelationResponse]:
    """Create multiple relations at once."""
    results: list[RelationResponse] = []
    for rel_data in relations:
        resp = await create_relation(source_id, rel_data, user_email)
        results.append(resp)
    return results
