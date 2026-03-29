"""Project type service — read templates from Shared/Projects/ and apply to projects."""

from __future__ import annotations

import json
import os
from typing import Any, Optional

import structlog

from core.config import _find_config_dir
from core.database import execute
from schemas.project_type import (
    ChatTemplate,
    PhaseFileContentResponse,
    PhaseFileResponse,
    ProjectTypeResponse,
    WorkflowTemplate,
)
from schemas.workflow import ProjectWorkflowCreate
from services.multi_workflow_service import create_workflow

log = structlog.get_logger(__name__)


def _shared_projects_dir() -> str:
    """Return the path to project type templates.

    Searches: config/Projects/, then Shared/Projects/ relative to config dir.
    """
    config_dir = _find_config_dir()
    # First try config/Projects/ (available in Docker via volume mount)
    candidate = os.path.join(config_dir, "Projects")
    if os.path.isdir(candidate):
        return candidate
    # Fallback: Shared/Projects/ (local dev)
    return os.path.join(config_dir, "..", "Shared", "Projects")


def _read_project_json(type_dir: str) -> Optional[dict[str, Any]]:
    """Read project.json from a project type directory."""
    path = os.path.join(type_dir, "project.json")
    if not os.path.isfile(path):
        return None
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _list_workflow_files(type_dir: str) -> list[str]:
    """List *.wrk.json files in a project type directory."""
    if not os.path.isdir(type_dir):
        return []
    return sorted(
        f for f in os.listdir(type_dir) if f.endswith(".wrk.json")
    )


def _build_project_type(
    type_id: str,
    data: dict[str, Any],
    type_dir: str,
) -> ProjectTypeResponse:
    """Build a ProjectTypeResponse from project.json data + discovered .wrk.json files."""
    workflows_cfg = data.get("workflows", [])
    workflows: list[WorkflowTemplate] = []
    known_filenames: set[str] = set()
    for w in workflows_cfg:
        fn = w.get("filename", "")
        if fn:
            known_filenames.add(fn)
        workflows.append(WorkflowTemplate(
            name=w.get("name", ""),
            filename=fn,
            type=w.get("type", "custom"),
            mode=w.get("mode", "sequential"),
            priority=w.get("priority", 50),
            depends_on=w.get("depends_on"),
        ))
    # Auto-discover .wrk.json files not listed in project.json
    for filename in _list_workflow_files(type_dir):
        if filename not in known_filenames:
            name = filename.replace(".wrk.json", "")
            workflows.append(WorkflowTemplate(
                name=name,
                filename=filename,
            ))
    chats_cfg = data.get("chats", [])
    chats: list[ChatTemplate] = []
    for c in chats_cfg:
        chats.append(ChatTemplate(
            id=c.get("id", ""),
            type=c.get("type", ""),
            agents=c.get("agents", []),
            source_prompt=c.get("source_prompt", ""),
        ))

    return ProjectTypeResponse(
        id=type_id,
        name=data.get("name", type_id),
        description=data.get("description", ""),
        team=data.get("team", ""),
        workflows=workflows,
        chats=chats,
    )


async def list_project_types(
    user_teams: Optional[list[str]] = None,
    role: Optional[str] = None,
) -> list[ProjectTypeResponse]:
    """List project types, filtered by user's accessible teams.

    Admins see all types. Members only see types whose ``team`` field
    matches one of their teams (case-insensitive).
    Types with no team field are visible to everyone.
    """
    base = _shared_projects_dir()
    if not os.path.isdir(base):
        return []

    # Normalise team names for case-insensitive comparison
    allowed = {t.lower() for t in (user_teams or [])} if role != "admin" else None

    results: list[ProjectTypeResponse] = []
    for entry in sorted(os.listdir(base)):
        type_dir = os.path.join(base, entry)
        if not os.path.isdir(type_dir):
            continue
        data = _read_project_json(type_dir)
        if data is None:
            continue
        # Filter by team access
        pt_team = data.get("team", "")
        if allowed is not None and pt_team and pt_team.lower() not in allowed:
            continue
        results.append(_build_project_type(entry, data, type_dir))
    return results


async def get_project_type(type_id: str) -> Optional[ProjectTypeResponse]:
    """Get a single project type with its workflow templates."""
    base = _shared_projects_dir()
    type_dir = os.path.join(base, type_id)
    data = _read_project_json(type_dir)
    if data is None:
        return None

    pt = _build_project_type(type_id, data, type_dir)

    # Enrich with discovered .wrk.json files not in project.json
    declared_filenames = {w.filename for w in pt.workflows}
    for fname in _list_workflow_files(type_dir):
        if fname not in declared_filenames:
            pt.workflows.append(WorkflowTemplate(
                name=fname.replace(".wrk.json", ""),
                filename=fname,
            ))

    return pt


def deduce_orchestrator_prompt(type_id: str, workflow_filename: str) -> str:
    """Walk the workflow phase chain to find the first non-external phase.

    Returns the orchestrator prompt filename for that phase.
    Raises ValueError if the workflow is misconfigured.
    """
    base = _shared_projects_dir()
    type_dir = os.path.join(base, type_id)
    current_filename = workflow_filename

    for _ in range(10):
        wrk_path = os.path.join(type_dir, current_filename)
        if not os.path.isfile(wrk_path):
            raise ValueError(f"Workflow introuvable : {current_filename}")

        with open(wrk_path, encoding="utf-8") as f:
            wrk = json.load(f)

        # Find phase with order: 1
        first_phase_id, first_phase = None, None
        for pid, pdata in wrk.get("phases", {}).items():
            if pdata.get("order") == 1:
                first_phase_id = pid
                first_phase = pdata
                break

        if not first_phase:
            raise ValueError(f"Aucune phase avec order:1 dans {current_filename}")

        # External phase → follow the reference
        if first_phase.get("type") == "external":
            ext = first_phase.get("external_workflow", "")
            if not ext:
                raise ValueError(
                    f"Phase externe sans external_workflow dans {current_filename}"
                )
            current_filename = ext
            continue

        # Internal phase found → derive prompt filename
        basename = current_filename.split(".")[0]
        return f"{basename}.wrk.phase.{first_phase_id}.md"

    raise ValueError("Cycle detecte : profondeur max (10) atteinte")


def list_phase_files(
    type_id: str,
    workflow_filename: str,
) -> list[PhaseFileResponse]:
    """List .wrk.phase.{id}.md files for a workflow inside a project type."""
    base = _shared_projects_dir()
    type_dir = os.path.join(base, type_id)
    if not os.path.isdir(type_dir):
        return []

    basename = workflow_filename.split(".")[0]
    prefix = f"{basename}.wrk.phase."
    suffix = ".md"

    results: list[PhaseFileResponse] = []
    for fname in sorted(os.listdir(type_dir)):
        if fname.startswith(prefix) and fname.endswith(suffix):
            phase_id = fname[len(prefix):-len(suffix)]
            results.append(PhaseFileResponse(phase_id=phase_id, filename=fname))
    return results


def resolve_workflow_phases(
    type_id: str,
    workflow_filename: str,
) -> list[dict[str, Any]]:
    """Return phases from a wrk.json, inlining external workflow phases."""
    base = _shared_projects_dir()
    type_dir = os.path.join(base, type_id)
    return _resolve_phases(type_dir, workflow_filename, depth=0)


def _resolve_phases(
    type_dir: str,
    workflow_filename: str,
    depth: int,
) -> list[dict[str, Any]]:
    if depth > 10:
        return []
    wrk_path = os.path.join(type_dir, workflow_filename)
    if not os.path.isfile(wrk_path):
        return []
    with open(wrk_path, encoding="utf-8") as f:
        wrk = json.load(f)
    phases = wrk.get("phases", {})
    if isinstance(phases, list):
        items = [(str(i), p) for i, p in enumerate(phases)]
    else:
        items = list(phases.items())
    # Sort by order
    items.sort(key=lambda x: x[1].get("order", 999))
    result: list[dict[str, Any]] = []
    for phase_id, phase_data in items:
        if phase_data.get("type") == "external" or phase_data.get("external_workflow"):
            ext_file = phase_data.get("external_workflow", "")
            if ext_file:
                ext_phases = _resolve_phases(type_dir, ext_file, depth + 1)
                result.extend(ext_phases)
            continue
        groups = phase_data.get("groups", [])
        deliverables: list[dict[str, str]] = []
        agents: set[str] = set()
        for g in groups:
            for d in g.get("deliverables", []):
                deliverables.append({
                    "key": d.get("id", ""),
                    "name": d.get("Name") or d.get("name") or d.get("id", ""),
                    "type": d.get("type", ""),
                })
                if d.get("agent"):
                    agents.add(d["agent"])
        result.append({
            "id": phase_id,
            "name": phase_data.get("name", phase_id),
            "order": phase_data.get("order", 0),
            "groups": len(groups),
            "deliverables": deliverables,
            "agents": sorted(agents),
            "humanGate": bool(phase_data.get("exit_conditions", {}).get("human_gate")),
        })
    return result


def read_phase_file(
    type_id: str,
    workflow_filename: str,
    phase_id: str,
) -> PhaseFileContentResponse | None:
    """Read the content of a single phase prompt file."""
    base = _shared_projects_dir()
    type_dir = os.path.join(base, type_id)
    basename = workflow_filename.split(".")[0]
    filename = f"{basename}.wrk.phase.{phase_id}.md"
    filepath = os.path.join(type_dir, filename)

    if not os.path.isfile(filepath):
        return None

    with open(filepath, encoding="utf-8") as f:
        content = f.read()
    return PhaseFileContentResponse(
        phase_id=phase_id,
        filename=filename,
        content=content,
    )


async def apply_project_type(
    project_slug: str,
    type_id: str,
    config: Optional[dict[str, str]] = None,
) -> list[int]:
    """Apply a project type to a project — creates N project_workflows.

    Returns the list of created workflow IDs.
    """
    pt = await get_project_type(type_id)
    if pt is None:
        return []

    # Remove existing workflows for this project (idempotent re-apply)
    await execute(
        "DELETE FROM project.project_workflows WHERE project_slug = $1",
        project_slug,
    )

    base = _shared_projects_dir()
    type_dir = os.path.join(base, type_id)

    # Map workflow name -> created ID for dependency resolution
    name_to_id: dict[str, int] = {}
    created_ids: list[int] = []

    for wt in pt.workflows:
        json_path = os.path.join(type_dir, wt.filename)
        depends_id: Optional[int] = None
        if wt.depends_on and wt.depends_on in name_to_id:
            depends_id = name_to_id[wt.depends_on]

        wf = await create_workflow(
            project_slug,
            ProjectWorkflowCreate(
                workflow_name=wt.name,
                workflow_type=wt.type,
                workflow_json_path=json_path,
                mode=wt.mode,
                priority=wt.priority,
                depends_on_workflow_id=depends_id,
                config=config or {},
            ),
        )
        name_to_id[wt.name] = wf.id
        created_ids.append(wf.id)

    log.info(
        "project_type_applied",
        project_slug=project_slug,
        type_id=type_id,
        workflow_count=len(created_ids),
    )
    return created_ids
