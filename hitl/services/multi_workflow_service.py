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


async def start_workflow(
    project_slug: str,
    workflow_id: int,
) -> dict:
    """Start a workflow: activate it, create first phase, dispatch agents for group A."""
    import json as _json
    import os

    import httpx

    from core.config import settings

    wf = await fetch_one(
        "SELECT id, workflow_name, workflow_json_path, status, team_id FROM project.project_workflows WHERE id = $1 AND project_slug = $2",
        workflow_id, project_slug,
    )
    if not wf:
        raise ValueError("Workflow not found")
    if wf["status"] not in ("pending", "paused"):
        raise ValueError("Workflow is already {}".format(wf["status"]))

    await execute(
        "UPDATE project.project_workflows SET status = 'active', started_at = NOW(), updated_at = NOW() WHERE id = $1",
        workflow_id,
    )

    wf_json_path = wf["workflow_json_path"] or ""
    wf_data = {}
    if os.path.isfile(wf_json_path):
        with open(wf_json_path, encoding="utf-8") as f:
            wf_data = _json.load(f)

    phases = wf_data.get("phases", {})
    if not phases:
        return {"ok": True, "workflow_id": workflow_id, "message": "No phases defined"}

    sorted_phases = sorted(phases.items(), key=lambda x: x[1].get("order", 0))
    # Skip external phases — find first normal phase with groups
    first_key, first_phase = None, None
    for pk, pv in sorted_phases:
        if pv.get("type") == "external":
            continue
        if pv.get("groups"):
            first_key, first_phase = pk, pv
            break
    if not first_key or not first_phase:
        return {"ok": True, "workflow_id": workflow_id, "message": "No actionable phases"}
    groups = first_phase.get("groups", [{"id": "A"}])
    first_group = groups[0] if groups else {"id": "A"}
    group_key = first_group.get("id", "A")

    phase_row = await fetch_one(
        """INSERT INTO project.workflow_phases
           (workflow_id, phase_key, phase_name, group_key, phase_order, group_order, iteration, status)
           VALUES ($1, $2, $3, $4, $5, 0, 1, 'running')
           RETURNING id""",
        workflow_id, first_key, first_phase.get("name", first_key), group_key,
        first_phase.get("order", 0),
    )
    phase_id = phase_row["id"] if phase_row else None

    if phase_id:
        await execute(
            "UPDATE project.project_workflows SET current_phase_id = $1 WHERE id = $2",
            phase_id, workflow_id,
        )

    gateway_url = settings.langgraph_api_url or "http://langgraph-api:8000"
    team_id = wf["team_id"] or ""
    thread_id = "workflow-{}".format(workflow_id)
    dispatched = []

    # Clean up orphaned tasks before dispatching new agents
    orphaned = await fetch_all(
        """UPDATE project.dispatcher_tasks
           SET status = 'timeout', completed_at = NOW(), error_message = 'Orphaned task cleaned before dispatch'
           WHERE project_slug = $1 AND workflow_id = $2
             AND status = 'running'
             AND started_at IS NOT NULL
             AND (started_at + (timeout_seconds || ' seconds')::interval) < NOW()
           RETURNING id, agent_id""",
        project_slug, workflow_id,
    )
    if orphaned:
        log.warning("orphaned_tasks_cleaned_before_dispatch", count=len(orphaned),
                    tasks=[{"id": str(o["id"]), "agent": o["agent_id"]} for o in orphaned])

    for deliv in first_group.get("deliverables", []):
        agent_id = deliv.get("agent", "")
        if not agent_id:
            continue
        d_name = deliv.get("Name") or deliv.get("name") or deliv.get("id", "")
        d_desc = deliv.get("description", "")
        instruction = (
            "Produis le livrable '{}'. {}\n\n"
            "IMPORTANT: Le contenu DOIT etre en format Markdown structure (titres, listes, tableaux). "
            "Ne jamais produire de JSON.\n\n"
            "Utilise save_deliverable avec deliverable_key='{}' pour sauvegarder le resultat."
        ).format(d_name, d_desc[:2000], deliv.get("id", d_name))

        task_row = await fetch_one(
            """INSERT INTO project.dispatcher_tasks
               (agent_id, team_id, thread_id, project_slug, phase, instruction, status, docker_image, workflow_id, phase_id, started_at, timeout_seconds)
               VALUES ($1, $2, $3, $4, $5, $6, 'running', 'gateway', $7, $8, NOW(), 2100)
               RETURNING id""",
            agent_id, team_id, thread_id, project_slug, first_key,
            instruction[:4000], workflow_id, phase_id,
        )

        if task_row:
            task_id = str(task_row["id"])
            try:
                async with httpx.AsyncClient(timeout=30) as client:
                    await client.post(
                        "{}/invoke".format(gateway_url),
                        json={
                            "messages": [{"role": "user", "content": instruction}],
                            "team_id": team_id,
                            "thread_id": thread_id,
                            "project_slug": project_slug,
                            "direct_agent": agent_id,
                            "workflow_id": workflow_id,
                            "phase_id": phase_id,
                            "task_id": task_id,
                        },
                    )
                dispatched.append(agent_id)
            except Exception as exc:
                log.error("start_workflow_dispatch_failed", agent=agent_id, error=str(exc)[:200])

    return {"ok": True, "workflow_id": workflow_id, "phase_id": phase_id, "dispatched": dispatched}


async def dispatch_group(project_slug: str, workflow_id: int, phase_id: int) -> dict:
    """Dispatch agents for an existing phase/group (must be pending)."""
    import json as _json
    import os

    import httpx

    from core.config import settings

    phase = await fetch_one(
        """SELECT wp.id, wp.phase_key, wp.group_key, wp.status,
                  pw.workflow_json_path, pw.team_id, pw.status as wf_status
           FROM project.workflow_phases wp
           JOIN project.project_workflows pw ON wp.workflow_id = pw.id
           WHERE wp.id = $1 AND pw.id = $2 AND pw.project_slug = $3""",
        phase_id, workflow_id, project_slug,
    )
    if not phase:
        raise ValueError("Phase not found")
    if phase["status"] != "pending":
        raise ValueError("Phase is already {}".format(phase["status"]))

    # Load workflow JSON to get deliverables for this group
    wf_json_path = phase["workflow_json_path"] or ""
    wf_data = {}
    if os.path.isfile(wf_json_path):
        with open(wf_json_path, encoding="utf-8") as f:
            wf_data = _json.load(f)

    phase_key = phase["phase_key"]
    group_key = phase["group_key"]
    phase_def = wf_data.get("phases", {}).get(phase_key, {})
    target_group = None
    for g in phase_def.get("groups", []):
        if g.get("id") == group_key:
            target_group = g
            break
    if not target_group:
        raise ValueError("Group {} not found in phase {}".format(group_key, phase_key))

    # Mark phase as running
    await execute(
        "UPDATE project.workflow_phases SET status = 'running', started_at = NOW() WHERE id = $1",
        phase_id,
    )
    await execute(
        "UPDATE project.project_workflows SET current_phase_id = $1 WHERE id = $2",
        phase_id, workflow_id,
    )

    gateway_url = settings.langgraph_api_url or "http://langgraph-api:8000"
    team_id = phase["team_id"] or ""
    thread_id = "workflow-{}".format(workflow_id)
    dispatched = []

    for deliv in target_group.get("deliverables", []):
        agent_id = deliv.get("agent", "")
        if not agent_id:
            continue
        d_name = deliv.get("Name") or deliv.get("name") or deliv.get("id", "")
        d_desc = deliv.get("description", "")
        instruction = (
            "Produis le livrable '{}'. {}\n\n"
            "IMPORTANT: Le contenu DOIT etre en format Markdown structure (titres, listes, tableaux). "
            "Ne jamais produire de JSON.\n\n"
            "Utilise save_deliverable avec deliverable_key='{}' pour sauvegarder le resultat."
        ).format(d_name, d_desc[:2000], deliv.get("id", d_name))

        task_row = await fetch_one(
            """INSERT INTO project.dispatcher_tasks
               (agent_id, team_id, thread_id, project_slug, phase, instruction, status, docker_image, workflow_id, phase_id, started_at, timeout_seconds)
               VALUES ($1, $2, $3, $4, $5, $6, 'running', 'gateway', $7, $8, NOW(), 2100)
               RETURNING id""",
            agent_id, team_id, thread_id, project_slug, phase_key,
            instruction[:4000], workflow_id, phase_id,
        )

        if task_row:
            task_id = str(task_row["id"])
            try:
                async with httpx.AsyncClient(timeout=30) as client:
                    await client.post(
                        "{}/invoke".format(gateway_url),
                        json={
                            "messages": [{"role": "user", "content": instruction}],
                            "team_id": team_id,
                            "thread_id": thread_id,
                            "project_slug": project_slug,
                            "direct_agent": agent_id,
                            "workflow_id": workflow_id,
                            "phase_id": phase_id,
                            "task_id": task_id,
                        },
                    )
                dispatched.append(agent_id)
            except Exception as exc:
                log.error("dispatch_group_failed", agent=agent_id, error=str(exc)[:200])

    return {"ok": True, "phase_id": phase_id, "dispatched": dispatched}
