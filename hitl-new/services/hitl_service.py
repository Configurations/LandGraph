"""HITL service — questions, answers, stats."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

import structlog

from core.database import execute, fetch_all, fetch_one
from schemas.common import SuccessResponse
from schemas.hitl import QuestionResponse, StatsResponse

log = structlog.get_logger(__name__)


def _row_to_question(row: dict) -> QuestionResponse:
    """Convert a DB row to a QuestionResponse."""
    ctx = row.get("context")
    if isinstance(ctx, str):
        try:
            ctx = json.loads(ctx)
        except (json.JSONDecodeError, TypeError):
            pass
    return QuestionResponse(
        id=row["id"],
        thread_id=row["thread_id"],
        agent_id=row["agent_id"],
        team_id=row["team_id"],
        request_type=row["request_type"],
        prompt=row["prompt"],
        context=ctx,
        channel=row.get("channel", ""),
        status=row["status"],
        response=row.get("response"),
        reviewer=row.get("reviewer"),
        created_at=row["created_at"],
        answered_at=row.get("answered_at"),
    )


async def list_questions(
    team_id: str,
    status: Optional[str] = None,
    channel: Optional[str] = None,
    offset: int = 0,
    limit: int = 50,
) -> list[QuestionResponse]:
    """List HITL questions for a team with optional filters."""
    conditions = ["team_id = $1"]
    params: list = [team_id]
    idx = 2

    if status:
        conditions.append("status = ${}".format(idx))
        params.append(status)
        idx += 1

    if channel:
        conditions.append("channel = ${}".format(idx))
        params.append(channel)
        idx += 1

    where = " AND ".join(conditions)
    query = (
        "SELECT * FROM project.hitl_requests"
        " WHERE {}"
        " ORDER BY created_at DESC"
        " OFFSET ${} LIMIT ${}"
    ).format(where, idx, idx + 1)
    params.extend([offset, limit])

    rows = await fetch_all(query, *params)
    return [_row_to_question(r) for r in rows]


async def get_question(question_id: UUID) -> QuestionResponse:
    """Get a single HITL question by ID."""
    row = await fetch_one(
        "SELECT * FROM project.hitl_requests WHERE id = $1",
        question_id,
    )
    if not row:
        from fastapi import HTTPException
        raise HTTPException(404, detail="hitl.question_not_found")
    return _row_to_question(row)


async def answer_question(
    question_id: UUID,
    response: str,
    action: str,
    reviewer: str,
) -> SuccessResponse:
    """Answer, approve, or reject a HITL question."""
    row = await fetch_one(
        "SELECT id, status FROM project.hitl_requests WHERE id = $1",
        question_id,
    )
    if not row:
        from fastapi import HTTPException
        raise HTTPException(404, detail="hitl.question_not_found")
    if row["status"] == "answered":
        from fastapi import HTTPException
        raise HTTPException(409, detail="hitl.already_answered")

    # Determine response value based on action
    if action == "approve":
        final_response = "approved"
    elif action == "reject":
        final_response = "rejected"
    else:
        final_response = response

    now = datetime.now(timezone.utc)
    await execute(
        """UPDATE project.hitl_requests
           SET status = 'answered',
               response = $1,
               reviewer = $2,
               response_channel = 'hitl-console',
               answered_at = $3
           WHERE id = $4""",
        final_response, reviewer, now, question_id,
    )
    log.info(
        "question_answered",
        question_id=str(question_id),
        action=action,
        reviewer=reviewer,
    )
    return SuccessResponse(ok=True)


async def get_stats(team_id: str) -> StatsResponse:
    """Get HITL request statistics for a team."""
    rows = await fetch_all(
        """SELECT status, COUNT(*) as cnt
           FROM project.hitl_requests
           WHERE team_id = $1
           GROUP BY status""",
        team_id,
    )
    counts: dict[str, int] = {}
    total = 0
    for r in rows:
        counts[r["status"]] = r["cnt"]
        total += r["cnt"]

    return StatsResponse(
        pending=counts.get("pending", 0),
        answered=counts.get("answered", 0),
        timeout=counts.get("timeout", 0),
        cancelled=counts.get("cancelled", 0),
        total=total,
    )
