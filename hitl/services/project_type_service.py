"""Project type service — read templates from Shared/Projects/ and apply to projects."""

from __future__ import annotations

import json
import os
from typing import Any, Optional

import structlog

from core.config import _find_config_dir
from core.database import execute
from schemas.project_type import ProjectTypeResponse, WorkflowTemplate
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
    """Build a ProjectTypeResponse from project.json data."""
    workflows_cfg = data.get("workflows", [])
    workflows: list[WorkflowTemplate] = []
    for w in workflows_cfg:
        workflows.append(WorkflowTemplate(
            name=w.get("name", ""),
            filename=w.get("filename", ""),
            type=w.get("type", "custom"),
            mode=w.get("mode", "sequential"),
            priority=w.get("priority", 50),
            depends_on=w.get("depends_on"),
        ))
    return ProjectTypeResponse(
        id=type_id,
        name=data.get("name", type_id),
        description=data.get("description", ""),
        team=data.get("team", ""),
        workflows=workflows,
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
