"""Multi-workflow management service — CRUD, lifecycle, transitions."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

import structlog

from core.database import execute, fetch_all, fetch_one
from schemas.workflow import ProjectWorkflowCreate, ProjectWorkflowResponse

log = structlog.get_logger(__name__)


def _row_to_response(row: Any) -> ProjectWorkflowResponse:
    """Map a database row to ProjectWorkflowResponse."""
    config_val = row["config"] or {}
    if isinstance(config_val, str):
        import json
        config_val = json.loads(config_val)
    return ProjectWorkflowResponse(
        id=row["id"],
        project_slug=row["project_slug"],
        workflow_name=row["workflow_name"],
        workflow_type=row["workflow_type"],
        workflow_json_path=row["workflow_json_path"],
        status=row["status"],
        mode=row["mode"],
        priority=row["priority"],
        iteration=row["iteration"],
        depends_on_workflow_id=row["depends_on_workflow_id"],
        config=config_val,
        started_at=str(row["started_at"]) if row["started_at"] else None,
        completed_at=str(row["completed_at"]) if row["completed_at"] else None,
        created_at=str(row["created_at"]) if row["created_at"] else None,
    )


async def list_workflows(
    project_slug: str,
    status: Optional[str] = None,
) -> list[ProjectWorkflowResponse]:
    """List all workflows for a project, optionally filtered by status."""
    if status:
        rows = await fetch_all(
            """SELECT * FROM project.project_workflows
               WHERE project_slug = $1 AND status = $2
               ORDER BY priority DESC, created_at""",
            project_slug, status,
        )
    else:
        rows = await fetch_all(
            """SELECT * FROM project.project_workflows
               WHERE project_slug = $1
               ORDER BY priority DESC, created_at""",
            project_slug,
        )
    return [_row_to_response(r) for r in rows]


async def get_workflow(workflow_id: int) -> Optional[ProjectWorkflowResponse]:
    """Get a single workflow by ID."""
    row = await fetch_one(
        "SELECT * FROM project.project_workflows WHERE id = $1",
        workflow_id,
    )
    if row is None:
        return None
    return _row_to_response(row)


async def create_workflow(
    project_slug: str,
    data: ProjectWorkflowCreate,
) -> ProjectWorkflowResponse:
    """Insert a new project workflow."""
    import json
    config_json = json.dumps(data.config, ensure_ascii=False)
    row = await fetch_one(
        """INSERT INTO project.project_workflows
               (project_slug, workflow_name, workflow_type, workflow_json_path,
                mode, priority, depends_on_workflow_id, config)
           VALUES ($1, $2, $3, $4, $5, $6, $7, $8::jsonb)
           RETURNING *""",
        project_slug,
        data.workflow_name,
        data.workflow_type,
        data.workflow_json_path,
        data.mode,
        data.priority,
        data.depends_on_workflow_id,
        config_json,
    )
    log.info("workflow_created", project_slug=project_slug, name=data.workflow_name)
    return _row_to_response(row)


async def activate_workflow(workflow_id: int) -> Optional[ProjectWorkflowResponse]:
    """Transition a workflow from pending to active."""
    now = datetime.now(timezone.utc)
    row = await fetch_one(
        """UPDATE project.project_workflows
           SET status = 'active', started_at = $1, updated_at = $1
           WHERE id = $2 AND status = 'pending'
           RETURNING *""",
        now, workflow_id,
    )
    if row is None:
        return None
    log.info("workflow_activated", workflow_id=workflow_id)
    return _row_to_response(row)


async def complete_workflow(workflow_id: int) -> Optional[ProjectWorkflowResponse]:
    """Mark a workflow as completed."""
    now = datetime.now(timezone.utc)
    row = await fetch_one(
        """UPDATE project.project_workflows
           SET status = 'completed', completed_at = $1, updated_at = $1
           WHERE id = $2 AND status = 'active'
           RETURNING *""",
        now, workflow_id,
    )
    if row is None:
        return None
    log.info("workflow_completed", workflow_id=workflow_id)
    return _row_to_response(row)


async def pause_workflow(workflow_id: int) -> Optional[ProjectWorkflowResponse]:
    """Pause an active workflow."""
    now = datetime.now(timezone.utc)
    row = await fetch_one(
        """UPDATE project.project_workflows
           SET status = 'paused', updated_at = $1
           WHERE id = $2 AND status = 'active'
           RETURNING *""",
        now, workflow_id,
    )
    if row is None:
        return None
    log.info("workflow_paused", workflow_id=workflow_id)
    return _row_to_response(row)


async def cancel_workflow(workflow_id: int) -> Optional[ProjectWorkflowResponse]:
    """Cancel a workflow (from pending, active, or paused)."""
    now = datetime.now(timezone.utc)
    row = await fetch_one(
        """UPDATE project.project_workflows
           SET status = 'cancelled', updated_at = $1
           WHERE id = $2 AND status IN ('pending', 'active', 'paused')
           RETURNING *""",
        now, workflow_id,
    )
    if row is None:
        return None
    log.info("workflow_cancelled", workflow_id=workflow_id)
    return _row_to_response(row)


async def resume_workflow(workflow_id: int) -> Optional[ProjectWorkflowResponse]:
    """Resume a paused workflow back to active."""
    now = datetime.now(timezone.utc)
    row = await fetch_one(
        """UPDATE project.project_workflows
           SET status = 'active', updated_at = $1
           WHERE id = $2 AND status = 'paused'
           RETURNING *""",
        now, workflow_id,
    )
    if row is None:
        return None
    log.info("workflow_resumed", workflow_id=workflow_id)
    return _row_to_response(row)


async def relaunch_workflow(workflow_id: int) -> Optional[ProjectWorkflowResponse]:
    """Re-launch a completed or cancelled workflow with incremented iteration."""
    original = await fetch_one(
        "SELECT * FROM project.project_workflows WHERE id = $1",
        workflow_id,
    )
    if original is None:
        return None
    if original["status"] not in ("completed", "cancelled"):
        return None

    import json
    config_json = json.dumps(original["config"] or {}, ensure_ascii=False)
    new_iteration = (original["iteration"] or 1) + 1
    row = await fetch_one(
        """INSERT INTO project.project_workflows
               (project_slug, workflow_name, workflow_type, workflow_json_path,
                mode, priority, depends_on_workflow_id, config, iteration)
           VALUES ($1, $2, $3, $4, $5, $6, $7, $8::jsonb, $9)
           RETURNING *""",
        original["project_slug"],
        original["workflow_name"],
        original["workflow_type"],
        original["workflow_json_path"],
        original["mode"],
        original["priority"],
        original["depends_on_workflow_id"],
        config_json,
        new_iteration,
    )
    log.info(
        "workflow_relaunched",
        original_id=workflow_id,
        new_id=row["id"],
        iteration=new_iteration,
    )
    return _row_to_response(row)


async def check_workflow_transitions(
    project_slug: str,
) -> list[ProjectWorkflowResponse]:
    """Check which pending workflows can now be activated.

    A pending workflow is activatable when it has no depends_on,
    or its dependency is completed.
    """
    rows = await fetch_all(
        """SELECT pw.*
           FROM project.project_workflows pw
           WHERE pw.project_slug = $1 AND pw.status = 'pending'
             AND (
                 pw.depends_on_workflow_id IS NULL
                 OR EXISTS (
                     SELECT 1 FROM project.project_workflows dep
                     WHERE dep.id = pw.depends_on_workflow_id
                       AND dep.status = 'completed'
                 )
             )
           ORDER BY pw.priority DESC, pw.created_at""",
        project_slug,
    )
    return [_row_to_response(r) for r in rows]


async def get_active_workflows(
    project_slug: str,
) -> list[ProjectWorkflowResponse]:
    """Return only active workflows for a project."""
    return await list_workflows(project_slug, status="active")
