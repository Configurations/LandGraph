"""Issue service helpers — row mapping, activity logging, notifications."""

from __future__ import annotations

from typing import Optional

from core.database import execute, fetch_all, fetch_one
from schemas.issue import IssueResponse


def row_to_response(row: dict) -> IssueResponse:
    """Map a database row to IssueResponse."""
    tags = row.get("tags") or []
    if isinstance(tags, str):
        tags = [t.strip() for t in tags.split(",") if t.strip()]
    return IssueResponse(
        id=row["id"],
        project_id=row["project_id"],
        title=row["title"],
        description=row["description"] or "",
        status=row["status"],
        priority=row["priority"],
        assignee=row["assignee"],
        team_id=row["team_id"],
        tags=tags,
        phase=row.get("phase"),
        created_by=row["created_by"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        is_blocked=row.get("is_blocked", False),
        blocking_count=int(row.get("blocking_count", 0)),
        blocked_by_count=int(row.get("blocked_by_count", 0)),
    )


async def fetch_issue_response(issue_id: str) -> Optional[IssueResponse]:
    """Re-fetch an issue as IssueResponse with blocking metadata."""
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
             WHERE target_issue_id = i.id AND type = 'blocks') AS blocked_by_count
        FROM project.pm_issues i
        WHERE i.id = $1
        """,
        issue_id,
    )
    if row is None:
        return None
    return row_to_response(row)


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


async def notify_on_update(
    current: dict,
    fields: dict,
    issue_id: str,
    user_email: str,
) -> None:
    """Send notifications when status or assignee changes."""
    from services.inbox_service import create_notification

    if "status" in fields and fields["status"] != current["status"]:
        old_status = current["status"]
        new_status = fields["status"]
        text = f"{user_email} changed {issue_id} from {old_status} to {new_status}"
        targets = set()
        if current["assignee"]:
            targets.add(current["assignee"])
        if current["created_by"]:
            targets.add(current["created_by"])
        targets.discard(user_email)
        for target in targets:
            await create_notification(target, "status", text, issue_id=issue_id)

    if "assignee" in fields and fields["assignee"] != current["assignee"]:
        new_assignee = fields["assignee"]
        if new_assignee and new_assignee != user_email:
            text = f"{user_email} assigned {issue_id} to you"
            await create_notification(new_assignee, "assign", text, issue_id=issue_id)


async def check_unblock_cascade(issue_id: str, user_email: str) -> None:
    """When an issue is done, check if issues it was blocking are now unblocked."""
    from services.inbox_service import create_notification

    blocked_rows = await fetch_all(
        """
        SELECT r.target_issue_id, i.assignee
        FROM project.pm_issue_relations r
        JOIN project.pm_issues i ON r.target_issue_id = i.id
        WHERE r.source_issue_id = $1 AND r.type = 'blocks'
        """,
        issue_id,
    )
    for br in blocked_rows:
        target_id = br["target_issue_id"]
        # Check if target still has other active blockers
        still_blocked = await fetch_one(
            """
            SELECT 1 FROM project.pm_issue_relations r
            JOIN project.pm_issues blocker ON r.source_issue_id = blocker.id
            WHERE r.target_issue_id = $1
              AND r.type = 'blocks'
              AND blocker.status != 'done'
              AND blocker.id != $2
            """,
            target_id, issue_id,
        )
        if still_blocked is None and br["assignee"]:
            text = f"{issue_id} is done — {target_id} is now unblocked"
            await create_notification(
                br["assignee"], "unblocked", text,
                issue_id=target_id, related_issue_id=issue_id,
            )
