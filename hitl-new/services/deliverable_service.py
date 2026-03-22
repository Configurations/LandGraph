"""Deliverable management service — list, detail, validate, remarks."""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Optional

import structlog

from core.config import settings
from core.database import execute, fetch_all, fetch_one
from schemas.deliverable import (
    DeliverableDetail,
    DeliverableResponse,
    RemarkResponse,
)
from services.validation_service import append_validation, copy_to_repo, read_file_content

log = structlog.get_logger(__name__)


async def list_deliverables(
    slug: str,
    phase: Optional[str] = None,
    agent_id: Optional[str] = None,
    status: Optional[str] = None,
) -> list[DeliverableResponse]:
    """List deliverables for a project with optional filters."""
    query = """
        SELECT a.id, a.task_id, a.key, a.deliverable_type, a.file_path,
               a.git_branch, a.category, a.status, a.reviewer,
               a.review_comment, a.reviewed_at, a.created_at,
               t.agent_id, t.phase, t.project_slug
        FROM project.dispatcher_task_artifacts a
        JOIN project.dispatcher_tasks t ON a.task_id = t.id
        WHERE t.project_slug = $1
    """
    args: list = [slug]
    idx = 2

    if phase is not None:
        query += f" AND t.phase = ${idx}"
        args.append(phase)
        idx += 1

    if agent_id is not None:
        query += f" AND t.agent_id = ${idx}"
        args.append(agent_id)
        idx += 1

    if status is not None:
        query += f" AND a.status = ${idx}"
        args.append(status)
        idx += 1

    query += " ORDER BY t.phase, a.created_at DESC"

    rows = await fetch_all(query, *args)
    return [
        DeliverableResponse(
            id=r["id"],
            task_id=str(r["task_id"]),
            key=r["key"],
            deliverable_type=r["deliverable_type"],
            file_path=r["file_path"],
            git_branch=r["git_branch"],
            category=r["category"],
            status=r["status"],
            reviewer=r["reviewer"],
            review_comment=r["review_comment"],
            reviewed_at=r["reviewed_at"],
            created_at=r["created_at"],
            agent_id=r["agent_id"],
            phase=r["phase"] or "",
            project_slug=r["project_slug"] or "",
        )
        for r in rows
    ]


async def get_deliverable(artifact_id: int) -> Optional[DeliverableDetail]:
    """Get a single deliverable with content and cost."""
    row = await fetch_one(
        """
        SELECT a.id, a.task_id, a.key, a.deliverable_type, a.file_path,
               a.git_branch, a.category, a.status, a.reviewer,
               a.review_comment, a.reviewed_at, a.created_at,
               t.agent_id, t.phase, t.project_slug, t.cost_usd
        FROM project.dispatcher_task_artifacts a
        JOIN project.dispatcher_tasks t ON a.task_id = t.id
        WHERE a.id = $1
        """,
        artifact_id,
    )
    if row is None:
        return None

    content = read_file_content(row["file_path"])
    cost = float(row["cost_usd"]) if row["cost_usd"] else 0.0

    return DeliverableDetail(
        id=row["id"],
        task_id=str(row["task_id"]),
        key=row["key"],
        deliverable_type=row["deliverable_type"],
        file_path=row["file_path"],
        git_branch=row["git_branch"],
        category=row["category"],
        status=row["status"],
        reviewer=row["reviewer"],
        review_comment=row["review_comment"],
        reviewed_at=row["reviewed_at"],
        created_at=row["created_at"],
        agent_id=row["agent_id"],
        phase=row["phase"] or "",
        project_slug=row["project_slug"] or "",
        content=content,
        cost_usd=cost,
    )


async def validate_deliverable(
    artifact_id: int,
    verdict: str,
    reviewer: str,
    comment: Optional[str] = None,
) -> bool:
    """Approve or reject a deliverable."""
    now = datetime.now(timezone.utc)
    result = await execute(
        """
        UPDATE project.dispatcher_task_artifacts
        SET status = $1, reviewer = $2, review_comment = $3, reviewed_at = $4
        WHERE id = $5
        """,
        verdict, reviewer, comment or "", now, artifact_id,
    )
    if result == "UPDATE 0":
        return False

    row = await fetch_one(
        """
        SELECT a.key, a.file_path, a.deliverable_type, a.category,
               t.project_slug
        FROM project.dispatcher_task_artifacts a
        JOIN project.dispatcher_tasks t ON a.task_id = t.id
        WHERE a.id = $1
        """,
        artifact_id,
    )
    if row:
        append_validation(
            row["project_slug"] or "",
            artifact_id,
            row["key"],
            verdict,
            reviewer,
            comment,
        )
        dtype = row["deliverable_type"] or ""
        if verdict == "approved" and dtype.startswith("delivers_docs"):
            await copy_to_repo(
                row["project_slug"] or "",
                row["key"],
                row["file_path"],
                row["category"],
                reviewer,
            )

    log.info(
        "deliverable_validated",
        artifact_id=artifact_id, verdict=verdict, reviewer=reviewer,
    )
    return True


async def submit_remark(
    artifact_id: int,
    reviewer: str,
    comment: str,
) -> RemarkResponse:
    """Add a remark to a deliverable."""
    row = await fetch_one(
        """
        INSERT INTO project.deliverable_remarks (artifact_id, reviewer, comment)
        VALUES ($1, $2, $3)
        RETURNING id, artifact_id, reviewer, comment, created_at
        """,
        artifact_id, reviewer, comment,
    )
    return RemarkResponse(
        id=row["id"],
        artifact_id=row["artifact_id"],
        reviewer=row["reviewer"],
        comment=row["comment"],
        created_at=row["created_at"],
    )


async def list_remarks(artifact_id: int) -> list[RemarkResponse]:
    """List all remarks for a deliverable."""
    rows = await fetch_all(
        """
        SELECT id, artifact_id, reviewer, comment, created_at
        FROM project.deliverable_remarks
        WHERE artifact_id = $1
        ORDER BY created_at
        """,
        artifact_id,
    )
    return [
        RemarkResponse(
            id=r["id"],
            artifact_id=r["artifact_id"],
            reviewer=r["reviewer"],
            comment=r["comment"],
            created_at=r["created_at"],
        )
        for r in rows
    ]


async def update_content(artifact_id: int, content: str) -> bool:
    """Update the markdown content of a deliverable on disk."""
    row = await fetch_one(
        "SELECT file_path FROM project.dispatcher_task_artifacts WHERE id = $1",
        artifact_id,
    )
    if not row or not row["file_path"]:
        return False

    fp = row["file_path"]
    full = (
        os.path.join(settings.ag_flow_root, fp)
        if not os.path.isabs(fp)
        else fp
    )
    try:
        os.makedirs(os.path.dirname(full), exist_ok=True)
        with open(full, "w", encoding="utf-8") as f:
            f.write(content)
        return True
    except OSError:
        log.error("deliverable_write_failed", artifact_id=artifact_id, path=full)
        return False
