"""Automation service — auto-approve rules, confidence scoring, stats."""

from __future__ import annotations

from typing import Any, Optional

import structlog

from core.database import execute, fetch_all, fetch_one
from schemas.automation import (
    AgentConfidenceResponse,
    AutomationRuleCreate,
    AutomationRuleResponse,
    AutomationStatsResponse,
)

log = structlog.get_logger(__name__)


def _row_to_rule(row: Any) -> AutomationRuleResponse:
    """Map a database row to AutomationRuleResponse."""
    return AutomationRuleResponse(
        id=row["id"],
        project_slug=row["project_slug"],
        workflow_type=row["workflow_type"],
        deliverable_type=row["deliverable_type"],
        auto_approve=row["auto_approve"],
        confidence_threshold=float(row["confidence_threshold"] or 0),
        min_approved_history=row["min_approved_history"],
        created_at=row["created_at"],
    )


async def list_rules(
    project_slug: Optional[str] = None,
) -> list[AutomationRuleResponse]:
    """List automation rules, optionally filtered by project."""
    if project_slug:
        rows = await fetch_all(
            """SELECT * FROM project.automation_rules
               WHERE project_slug = $1 OR project_slug IS NULL
               ORDER BY id""",
            project_slug,
        )
    else:
        rows = await fetch_all(
            "SELECT * FROM project.automation_rules ORDER BY id",
        )
    return [_row_to_rule(r) for r in rows]


async def create_rule(data: AutomationRuleCreate) -> AutomationRuleResponse:
    """Insert a new automation rule."""
    row = await fetch_one(
        """INSERT INTO project.automation_rules
               (project_slug, workflow_type, deliverable_type,
                auto_approve, confidence_threshold, min_approved_history)
           VALUES ($1, $2, $3, $4, $5, $6)
           RETURNING *""",
        data.project_slug,
        data.workflow_type,
        data.deliverable_type,
        data.auto_approve,
        data.confidence_threshold,
        data.min_approved_history,
    )
    log.info("automation_rule_created", rule_id=row["id"])
    return _row_to_rule(row)


async def update_rule(
    rule_id: int,
    data: AutomationRuleCreate,
) -> Optional[AutomationRuleResponse]:
    """Update an existing automation rule."""
    row = await fetch_one(
        """UPDATE project.automation_rules
           SET project_slug = $1, workflow_type = $2, deliverable_type = $3,
               auto_approve = $4, confidence_threshold = $5, min_approved_history = $6
           WHERE id = $7
           RETURNING *""",
        data.project_slug,
        data.workflow_type,
        data.deliverable_type,
        data.auto_approve,
        data.confidence_threshold,
        data.min_approved_history,
        rule_id,
    )
    if row is None:
        return None
    log.info("automation_rule_updated", rule_id=rule_id)
    return _row_to_rule(row)


async def delete_rule(rule_id: int) -> bool:
    """Delete an automation rule. Returns True if deleted."""
    result = await execute(
        "DELETE FROM project.automation_rules WHERE id = $1",
        rule_id,
    )
    return result != "DELETE 0"


async def get_agent_confidence(
    agent_id: str,
    deliverable_type: Optional[str] = None,
) -> AgentConfidenceResponse:
    """Compute agent confidence from historical approvals/rejections."""
    if deliverable_type:
        row = await fetch_one(
            """SELECT
                   COUNT(*) AS total,
                   COUNT(*) FILTER (WHERE a.status = 'approved') AS approved,
                   COUNT(*) FILTER (WHERE a.status = 'rejected') AS rejected
               FROM project.dispatcher_task_artifacts a
               JOIN project.dispatcher_tasks t ON a.task_id = t.id
               WHERE t.agent_id = $1
                 AND a.deliverable_type = $2
                 AND a.status IN ('approved', 'rejected')""",
            agent_id, deliverable_type,
        )
    else:
        row = await fetch_one(
            """SELECT
                   COUNT(*) AS total,
                   COUNT(*) FILTER (WHERE a.status = 'approved') AS approved,
                   COUNT(*) FILTER (WHERE a.status = 'rejected') AS rejected
               FROM project.dispatcher_task_artifacts a
               JOIN project.dispatcher_tasks t ON a.task_id = t.id
               WHERE t.agent_id = $1
                 AND a.status IN ('approved', 'rejected')""",
            agent_id,
        )

    total = row["total"] if row else 0
    approved = row["approved"] if row else 0
    rejected = row["rejected"] if row else 0
    confidence = approved / total if total > 0 else 0.0

    return AgentConfidenceResponse(
        agent_id=agent_id,
        deliverable_type=deliverable_type or "",
        total=total,
        approved=approved,
        rejected=rejected,
        confidence=round(confidence, 4),
    )


async def check_auto_approve(artifact_id: int) -> bool:
    """Check whether an artifact should be auto-approved based on rules.

    Returns True if auto-approval should proceed.
    """
    row = await fetch_one(
        """SELECT a.deliverable_type, t.agent_id, t.project_slug, pw.workflow_type
           FROM project.dispatcher_task_artifacts a
           JOIN project.dispatcher_tasks t ON a.task_id = t.id
           LEFT JOIN project.project_workflows pw ON t.workflow_id = pw.id
           WHERE a.id = $1""",
        artifact_id,
    )
    if row is None:
        return False

    d_type = row["deliverable_type"]
    agent_id = row["agent_id"]
    slug = row["project_slug"]
    wf_type = row["workflow_type"]

    # Find matching rule (project-specific first, then global)
    rule = await _find_matching_rule(slug, wf_type, d_type)
    if rule is None or not rule["auto_approve"]:
        return False

    threshold = float(rule["confidence_threshold"] or 0)
    min_history = rule["min_approved_history"] or 5

    conf = await get_agent_confidence(agent_id, d_type)
    if conf.total < min_history:
        log.debug(
            "auto_approve_skipped_insufficient_history",
            artifact_id=artifact_id,
            total=conf.total,
            min_required=min_history,
        )
        return False

    if conf.confidence < threshold:
        log.debug(
            "auto_approve_skipped_low_confidence",
            artifact_id=artifact_id,
            confidence=conf.confidence,
            threshold=threshold,
        )
        return False

    log.info(
        "auto_approve_eligible",
        artifact_id=artifact_id,
        confidence=conf.confidence,
        threshold=threshold,
    )
    return True


async def _find_matching_rule(
    project_slug: Optional[str],
    workflow_type: Optional[str],
    deliverable_type: str,
) -> Optional[Any]:
    """Find the most specific matching automation rule."""
    # 1. Exact match: project + workflow_type + deliverable_type
    if project_slug and workflow_type:
        row = await fetch_one(
            """SELECT * FROM project.automation_rules
               WHERE project_slug = $1 AND workflow_type = $2 AND deliverable_type = $3""",
            project_slug, workflow_type, deliverable_type,
        )
        if row:
            return row

    # 2. Project + deliverable_type (any workflow type)
    if project_slug:
        row = await fetch_one(
            """SELECT * FROM project.automation_rules
               WHERE project_slug = $1 AND workflow_type IS NULL AND deliverable_type = $2""",
            project_slug, deliverable_type,
        )
        if row:
            return row

    # 3. Global rule (no project slug)
    row = await fetch_one(
        """SELECT * FROM project.automation_rules
           WHERE project_slug IS NULL AND deliverable_type = $1""",
        deliverable_type,
    )
    return row


async def get_automation_stats(
    project_slug: str,
) -> AutomationStatsResponse:
    """Compute automation statistics for a project."""
    row = await fetch_one(
        """SELECT
               COUNT(*) FILTER (WHERE a.status IN ('approved', 'rejected')) AS total_reviewed,
               COUNT(*) FILTER (WHERE a.status = 'approved' AND a.reviewer = 'auto') AS auto_approved,
               COUNT(*) FILTER (WHERE a.status = 'approved' AND a.reviewer != 'auto') AS manual_approved,
               COUNT(*) FILTER (WHERE a.status = 'rejected') AS rejected
           FROM project.dispatcher_task_artifacts a
           JOIN project.dispatcher_tasks t ON a.task_id = t.id
           WHERE t.project_slug = $1""",
        project_slug,
    )
    total = row["total_reviewed"] if row else 0
    auto_app = row["auto_approved"] if row else 0
    manual_app = row["manual_approved"] if row else 0
    rej = row["rejected"] if row else 0

    return AutomationStatsResponse(
        total_reviewed=total,
        auto_approved=auto_app,
        manual_approved=manual_app,
        rejected=rej,
        auto_pct=round(auto_app / total * 100, 1) if total > 0 else 0.0,
        manual_pct=round(manual_app / total * 100, 1) if total > 0 else 0.0,
        rejected_pct=round(rej / total * 100, 1) if total > 0 else 0.0,
    )
