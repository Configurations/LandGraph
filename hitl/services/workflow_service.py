"""Workflow visualization service — read Workflow.json, resolve agent/deliverable statuses."""

from __future__ import annotations

import json
import os
from typing import Any, Optional

import structlog

from core.config import _find_config_dir, load_teams
from core.database import fetch_all, fetch_one
from schemas.workflow import (
    PhaseAgent,
    PhaseDeliverable,
    PhaseStatus,
    WorkflowStatusResponse,
)

log = structlog.get_logger(__name__)


async def _get_project_team(slug: str) -> Optional[str]:
    """Look up the team_id for a project by slug."""
    row = await fetch_one(
        "SELECT team_id FROM project.pm_projects WHERE slug = $1", slug,
    )
    if row is None:
        return None
    return row["team_id"]


def _team_directory(team_id: str) -> Optional[str]:
    """Resolve the team directory name from teams.json."""
    teams = load_teams()
    for t in teams:
        if t["id"] == team_id:
            return t.get("directory", team_id)
    return None


def _read_workflow_json(team_id: str) -> Optional[dict[str, Any]]:
    """Read Workflow.json for a team, with fallback to Shared."""
    config_dir = _find_config_dir()
    team_dir = _team_directory(team_id)
    if not team_dir:
        return None

    # Primary: config/Teams/<dir>/Workflow.json
    primary = os.path.join(config_dir, "Teams", team_dir, "Workflow.json")
    if os.path.isfile(primary):
        with open(primary, encoding="utf-8") as f:
            return json.load(f)

    # Fallback: Shared/Teams/<dir>/Workflow.json
    shared = os.path.join(config_dir, "..", "Shared", "Teams", team_dir, "Workflow.json")
    if os.path.isfile(shared):
        with open(shared, encoding="utf-8") as f:
            return json.load(f)

    log.warning("workflow_json_not_found", team_id=team_id)
    return None


def _read_registry_json(team_id: str) -> dict[str, Any]:
    """Read agents_registry.json for agent name lookup."""
    config_dir = _find_config_dir()
    team_dir = _team_directory(team_id)
    if not team_dir:
        return {}

    path = os.path.join(config_dir, "Teams", team_dir, "agents_registry.json")
    if os.path.isfile(path):
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
            return data.get("agents", {})
    return {}


async def _resolve_agent_status(
    project_slug: str,
    phase_id: str,
    agent_id: str,
    workflow_id: Optional[int] = None,
) -> tuple[str, Optional[str]]:
    """Check dispatcher_tasks for agent status in a phase. Returns (status, task_id)."""
    if workflow_id is not None:
        row = await fetch_one(
            """
            SELECT id, status FROM project.dispatcher_tasks
            WHERE project_slug = $1 AND phase = $2 AND agent_id = $3 AND workflow_id = $4
            ORDER BY created_at DESC LIMIT 1
            """,
            project_slug, phase_id, agent_id, workflow_id,
        )
    else:
        row = await fetch_one(
            """
            SELECT id, status FROM project.dispatcher_tasks
            WHERE project_slug = $1 AND phase = $2 AND agent_id = $3
            ORDER BY created_at DESC LIMIT 1
            """,
            project_slug, phase_id, agent_id,
        )
    if row is None:
        return "pending", None

    task_status = row["status"]
    task_id = str(row["id"])

    if task_status == "success":
        return "completed", task_id
    if task_status in ("running", "waiting_hitl"):
        return "active", task_id
    if task_status in ("failure", "timeout"):
        return "failed", task_id
    return "pending", task_id


async def _resolve_deliverable_status(
    project_slug: str,
    phase_id: str,
    agent_id: str,
    deliverable_key: str,
    workflow_id: Optional[int] = None,
) -> tuple[str, Optional[int]]:
    """Check dispatcher_task_artifacts for deliverable status. Returns (status, artifact_id)."""
    if workflow_id is not None:
        row = await fetch_one(
            """
            SELECT a.id, a.status
            FROM project.dispatcher_task_artifacts a
            JOIN project.dispatcher_tasks t ON a.task_id = t.id
            WHERE t.project_slug = $1 AND t.phase = $2 AND t.agent_id = $3
              AND a.key = $4 AND t.workflow_id = $5
            ORDER BY a.created_at DESC LIMIT 1
            """,
            project_slug, phase_id, agent_id, deliverable_key, workflow_id,
        )
    else:
        row = await fetch_one(
            """
            SELECT a.id, a.status
            FROM project.dispatcher_task_artifacts a
            JOIN project.dispatcher_tasks t ON a.task_id = t.id
            WHERE t.project_slug = $1 AND t.phase = $2 AND t.agent_id = $3 AND a.key = $4
            ORDER BY a.created_at DESC LIMIT 1
            """,
            project_slug, phase_id, agent_id, deliverable_key,
        )
    if row is None:
        return "pending", None

    art_status = row["status"]
    art_id = row["id"]

    if art_status == "approved":
        return "completed", art_id
    if art_status == "rejected":
        return "rejected", art_id
    return "in_progress", art_id


def _determine_phase_status(agents: list[PhaseAgent]) -> str:
    """Determine the overall phase status from its agents."""
    statuses = {a.status for a in agents}
    if not statuses or statuses == {"pending"}:
        return "pending"
    if statuses == {"completed"}:
        return "completed"
    if "failed" in statuses:
        return "failed"
    if "active" in statuses:
        return "active"
    return "in_progress"


async def _read_workflow_json_for_workflow_id(
    workflow_id: int,
) -> Optional[dict[str, Any]]:
    """Read workflow JSON from the path stored in project_workflows table."""
    row = await fetch_one(
        "SELECT workflow_json_path FROM project.project_workflows WHERE id = $1",
        workflow_id,
    )
    if row is None or not row["workflow_json_path"]:
        return None
    import os
    path = row["workflow_json_path"]
    if os.path.isfile(path):
        with open(path, encoding="utf-8") as f:
            import json
            return json.load(f)
    log.warning("workflow_json_path_not_found", workflow_id=workflow_id, path=path)
    return None


async def get_workflow_status(
    project_slug: str,
    team_id: str,
    workflow_id: Optional[int] = None,
) -> WorkflowStatusResponse:
    """Build the full workflow status for a project.

    If workflow_id is provided, read the workflow JSON from the
    project_workflows table path instead of the default team Workflow.json.
    """
    if workflow_id is not None:
        wf = await _read_workflow_json_for_workflow_id(workflow_id)
    else:
        wf = _read_workflow_json(team_id)
    if wf is None:
        return WorkflowStatusResponse(phases=[], total_phases=0, completed_phases=0)

    registry = _read_registry_json(team_id)
    raw_phases = wf.get("phases", {})
    # Support both dict (real Workflow.json) and list (test fixtures)
    if isinstance(raw_phases, dict):
        phases_items = [(pid, pcfg) for pid, pcfg in raw_phases.items()]
    else:
        phases_items = [(p.get("id", ""), p) for p in raw_phases]

    phases: list[PhaseStatus] = []
    current_phase: Optional[str] = None
    completed_count = 0

    for phase_id, phase_cfg in phases_items:
        phase_name = phase_cfg.get("name", phase_id)

        # Flatten deliverables from groups (new format)
        agents: list[PhaseAgent] = []
        agent_ids_seen: set[str] = set()
        deliverables_cfg = []
        for group in phase_cfg.get("groups", []):
            gid = group.get("id", "")
            for d in group.get("deliverables", []):
                key = f"{gid}:{d.get('id', '')}"
                deliverables_cfg.append({"key": key, **d})

        for deliv in deliverables_cfg:
            aid = deliv.get("agent", "")
            if aid and aid not in agent_ids_seen:
                agent_ids_seen.add(aid)
                agent_name = registry.get(aid, {}).get("name", aid)
                status, task_id = await _resolve_agent_status(
                    project_slug, phase_id, aid, workflow_id,
                )
                agents.append(PhaseAgent(
                    agent_id=aid, name=agent_name, status=status, task_id=task_id,
                ))

        # Resolve deliverables
        deliverables: list[PhaseDeliverable] = []
        for deliv in deliverables_cfg:
            key = deliv.get("key", "")
            aid = deliv.get("agent", "")
            d_status, art_id = await _resolve_deliverable_status(
                project_slug, phase_id, aid, key, workflow_id,
            )
            deliverables.append(PhaseDeliverable(
                key=key,
                agent_id=aid,
                deliverable_type=deliv.get("type", deliv.get("deliverable_type", "")),
                category=deliv.get("category"),
                required=deliv.get("required", True),
                status=d_status,
                artifact_id=art_id,
            ))

        phase_status = _determine_phase_status(agents)
        if phase_status == "completed":
            completed_count += 1
        if phase_status == "active" and current_phase is None:
            current_phase = phase_id

        phases.append(PhaseStatus(
            id=phase_id, name=phase_name, status=phase_status,
            agents=agents, deliverables=deliverables,
        ))

    return WorkflowStatusResponse(
        phases=phases,
        current_phase=current_phase,
        total_phases=len(phases),
        completed_phases=completed_count,
    )


async def get_phase_detail(
    project_slug: str,
    team_id: str,
    phase_id: str,
) -> Optional[PhaseStatus]:
    """Get detail for a single workflow phase."""
    result = await get_workflow_status(project_slug, team_id)
    for phase in result.phases:
        if phase.id == phase_id:
            return phase
    return None


async def get_workflow_phases_detail(
    project_slug: str,
    workflow_id: int,
):
    """Get all phases for a workflow with deliverables including file content.

    Reads the workflow JSON to know what deliverables are expected,
    then enriches with DB data (artifacts produced, status, content).
    """
    import json as _json
    from schemas.workflow import DeliverableWithContent, PhaseDetailResponse, WorkflowPhasesResponse

    wf = await fetch_one(
        "SELECT id, workflow_name, workflow_json_path, status FROM project.project_workflows WHERE id = $1 AND project_slug = $2",
        workflow_id, project_slug,
    )
    if not wf:
        return None

    # Read workflow JSON for expected structure
    wf_json_path = wf["workflow_json_path"] or ""
    wf_data = {}
    if os.path.isfile(wf_json_path):
        try:
            with open(wf_json_path, encoding="utf-8") as f:
                wf_data = _json.load(f)
        except Exception:
            pass

    # Get runtime phases from DB
    db_phases = await fetch_all(
        """SELECT id, phase_key, phase_name, group_key, status
           FROM project.workflow_phases
           WHERE workflow_id = $1
           ORDER BY phase_order DESC, group_order DESC""",
        workflow_id,
    )
    # Index DB phases by phase_key+group_key
    db_phase_map = {}
    for p in db_phases:
        key = "{}:{}".format(p["phase_key"] or "", p["group_key"] or "A")
        db_phase_map[key] = p

    # Get all artifacts for this workflow
    all_artifacts = await fetch_all(
        """SELECT a.id, a.key, a.status, a.version, a.file_path,
                  a.reviewer, a.review_comment, a.reviewed_at::text, a.created_at::text,
                  t.agent_id, t.phase_id
           FROM project.dispatcher_task_artifacts a
           JOIN project.dispatcher_tasks t ON a.task_id = t.id
           WHERE t.project_slug = $1 AND t.workflow_id = $2
           ORDER BY a.created_at""",
        project_slug, workflow_id,
    )
    # Mark orphaned tasks as timeout (running past their timeout_seconds)
    orphaned = await fetch_all(
        """UPDATE project.dispatcher_tasks
           SET status = 'timeout', completed_at = NOW(), error_message = 'Orphaned task detected by poll'
           WHERE project_slug = $1 AND workflow_id = $2
             AND status = 'running'
             AND started_at IS NOT NULL
             AND (started_at + (timeout_seconds || ' seconds')::interval) < NOW()
           RETURNING id, agent_id""",
        project_slug, workflow_id,
    )
    if orphaned:
        log.warning("orphaned_tasks_detected", count=len(orphaned),
                    tasks=[{"id": str(o["id"]), "agent": o["agent_id"]} for o in orphaned])

    # Index artifacts by phase_id + key, and also by phase_id + agent_id as fallback
    artifact_map = {}
    artifact_by_agent = {}
    for a in all_artifacts:
        artifact_map["{}:{}".format(a["phase_id"] or 0, a["key"])] = a
        artifact_by_agent["{}:{}".format(a["phase_id"] or 0, a["agent_id"])] = a

    # Check for pending human gate
    thread_id = "workflow-{}".format(workflow_id)
    gate = await fetch_one(
        """SELECT id, prompt, agent_id, created_at::text
           FROM project.hitl_requests
           WHERE thread_id = $1 AND status = 'pending'
           ORDER BY created_at DESC LIMIT 1""",
        thread_id,
    )
    human_gate = None
    if gate:
        human_gate = {
            "id": str(gate["id"]),
            "prompt": gate["prompt"],
            "agent_id": gate["agent_id"],
            "created_at": gate["created_at"],
        }

    ag_flow_root = os.getenv("AG_FLOW_ROOT", "/root/ag.flow")

    def _read_file(file_path):
        if not file_path:
            return ""
        fpath = os.path.join(ag_flow_root, file_path) if not os.path.isabs(file_path) else file_path
        if os.path.isfile(fpath):
            try:
                with open(fpath, encoding="utf-8") as f:
                    return f.read()
            except Exception:
                pass
        return ""

    # Build phase details from JSON structure
    phase_details = []
    json_phases = wf_data.get("phases", {})

    # Current phase from DB
    current_phase_row = await fetch_one(
        "SELECT current_phase_id FROM project.project_workflows WHERE id = $1", workflow_id,
    )
    current_phase_id = current_phase_row["current_phase_id"] if current_phase_row else None

    for phase_key, phase_def in sorted(json_phases.items(), key=lambda x: x[1].get("order", 0)):
        phase_type = phase_def.get("type", "normal")
        if phase_type == "external":
            continue

        groups = phase_def.get("groups", [])
        if not groups:
            continue

        for group in groups:
            group_key = group.get("id", "A")
            db_key = "{}:{}".format(phase_key, group_key)
            db_phase = db_phase_map.get(db_key)

            # Only show phases that exist in DB (running or completed) — not future phases
            if not db_phase:
                continue

            phase_status = db_phase["status"]
            phase_db_id = db_phase["id"]

            # Build deliverables from JSON definition
            deliverable_list = []
            for d in group.get("deliverables", []):
                d_key = d.get("id", "")
                d_name = d.get("Name") or d.get("name") or d_key
                agent_id = d.get("agent", "")

                # Check if artifact exists in DB (by key, then fallback by agent_id)
                art_key = "{}:{}".format(phase_db_id, d_key)
                art = artifact_map.get(art_key)
                if not art:
                    art = artifact_by_agent.get("{}:{}".format(phase_db_id, agent_id))

                if art:
                    content = _read_file(art["file_path"])
                    deliverable_list.append(DeliverableWithContent(
                        id=art["id"],
                        key=d_name,
                        agent_id=art["agent_id"] or agent_id,
                        agent_name=art["agent_id"] or agent_id,
                        status=art["status"] or "pending",
                        version=art["version"] or 1,
                        file_path=art["file_path"],
                        content=content,
                        reviewer=art["reviewer"],
                        review_comment=art["review_comment"],
                        reviewed_at=art["reviewed_at"],
                        created_at=art["created_at"],
                    ))
                else:
                    # No artifact yet — show as expected deliverable
                    deliverable_list.append(DeliverableWithContent(
                        id=0,
                        key=d_name,
                        agent_id=agent_id,
                        agent_name=agent_id,
                        status="running" if phase_status == "running" else "pending",
                        version=0,
                    ))

            phase_details.append(PhaseDetailResponse(
                id=phase_db_id,
                phase_key=phase_key,
                phase_name=phase_def.get("name", phase_key),
                group_key=group_key,
                status=phase_status,
                deliverables=deliverable_list,
            ))

    # Sort: running phases first, then by order (already sorted), most recent first
    phase_details.sort(key=lambda p: (0 if p.status == "running" else 1 if p.status == "completed" else 2))

    return WorkflowPhasesResponse(
        workflow_id=workflow_id,
        workflow_name=wf["workflow_name"],
        status=wf["status"],
        human_gate=human_gate,
        phases=phase_details,
    )
