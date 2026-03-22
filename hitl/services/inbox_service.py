"""Inbox notification service — list, read, create."""

from __future__ import annotations

from typing import Optional

import structlog

from core.database import execute, fetch_all, fetch_one
from schemas.inbox import NotificationResponse

log = structlog.get_logger(__name__)


async def list_notifications(
    user_email: str,
    limit: int = 100,
) -> list[NotificationResponse]:
    """List notifications for a user, newest first."""
    rows = await fetch_all(
        """
        SELECT id, user_email, type, text, issue_id,
               related_issue_id, relation_type, avatar, read, created_at
        FROM project.pm_inbox
        WHERE user_email = $1
        ORDER BY created_at DESC
        LIMIT $2
        """,
        user_email, limit,
    )
    return [_row_to_notification(r) for r in rows]


async def mark_read(notif_id: int, user_email: str) -> bool:
    """Mark a single notification as read."""
    result = await execute(
        "UPDATE project.pm_inbox SET read = TRUE WHERE id = $1 AND user_email = $2",
        notif_id, user_email,
    )
    return result != "UPDATE 0"


async def mark_all_read(user_email: str) -> int:
    """Mark all unread notifications as read. Returns count updated."""
    result = await execute(
        "UPDATE project.pm_inbox SET read = TRUE WHERE user_email = $1 AND read = FALSE",
        user_email,
    )
    # result is like "UPDATE 5"
    try:
        return int(result.split(" ")[1])
    except (IndexError, ValueError):
        return 0


async def get_unread_count(user_email: str) -> int:
    """Return number of unread notifications."""
    row = await fetch_one(
        "SELECT COUNT(*) AS cnt FROM project.pm_inbox WHERE user_email = $1 AND read = FALSE",
        user_email,
    )
    return row["cnt"] if row else 0


async def create_notification(
    user_email: str,
    type: str,
    text: str,
    issue_id: Optional[str] = None,
    related_issue_id: Optional[str] = None,
    relation_type: Optional[str] = None,
    avatar: Optional[str] = None,
) -> None:
    """Insert a notification into pm_inbox."""
    await execute(
        """
        INSERT INTO project.pm_inbox
            (user_email, type, text, issue_id, related_issue_id, relation_type, avatar)
        VALUES ($1, $2, $3, $4, $5, $6, $7)
        """,
        user_email, type, text, issue_id, related_issue_id, relation_type, avatar,
    )
    log.debug("notification_created", user_email=user_email, type=type, issue_id=issue_id)


def _row_to_notification(row: dict) -> NotificationResponse:
    """Map a database row to NotificationResponse."""
    return NotificationResponse(
        id=row["id"],
        user_email=row["user_email"],
        type=row["type"],
        text=row["text"],
        issue_id=row["issue_id"],
        related_issue_id=row["related_issue_id"],
        relation_type=row["relation_type"],
        avatar=row["avatar"],
        read=row["read"],
        created_at=row["created_at"],
    )
