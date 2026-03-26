"""Project type template routes."""

from __future__ import annotations

import structlog
from fastapi import APIRouter, Depends, HTTPException

from core.security import TokenData, get_current_user
from schemas.project_type import (
    ApplyProjectTypeRequest,
    PhaseFileContentResponse,
    PhaseFileResponse,
    ProjectTypeResponse,
)
from services import project_type_service

log = structlog.get_logger(__name__)

router = APIRouter(tags=["project-types"])


@router.get("/api/project-types", response_model=list[ProjectTypeResponse])
async def list_project_types(
    user: TokenData = Depends(get_current_user),
) -> list[ProjectTypeResponse]:
    """List project type templates accessible to the current user."""
    return await project_type_service.list_project_types(
        user_teams=user.teams,
        role=user.role,
    )


@router.get("/api/project-types/{type_id}", response_model=ProjectTypeResponse)
async def get_project_type(
    type_id: str,
    user: TokenData = Depends(get_current_user),
) -> ProjectTypeResponse:
    """Get a single project type with its workflow templates."""
    pt = await project_type_service.get_project_type(type_id)
    if pt is None:
        raise HTTPException(status_code=404, detail="project_type.not_found")
    return pt


@router.get(
    "/api/project-types/{type_id}/workflows/{wf_filename}/phase-files",
    response_model=list[PhaseFileResponse],
)
async def list_phase_files(
    type_id: str,
    wf_filename: str,
    user: TokenData = Depends(get_current_user),
) -> list[PhaseFileResponse]:
    """List phase prompt files for a workflow in a project type."""
    return project_type_service.list_phase_files(type_id, wf_filename)


@router.get(
    "/api/project-types/{type_id}/workflows/{wf_filename}/phase-files/{phase_id}",
    response_model=PhaseFileContentResponse,
)
async def read_phase_file(
    type_id: str,
    wf_filename: str,
    phase_id: str,
    user: TokenData = Depends(get_current_user),
) -> PhaseFileContentResponse:
    """Read the content of a phase prompt file."""
    result = project_type_service.read_phase_file(type_id, wf_filename, phase_id)
    if result is None:
        raise HTTPException(status_code=404, detail="phase_file.not_found")
    return result


@router.post("/api/projects/{slug}/apply-type/{type_id}")
async def apply_project_type(
    slug: str,
    type_id: str,
    body: ApplyProjectTypeRequest = ApplyProjectTypeRequest(),
    user: TokenData = Depends(get_current_user),
) -> dict:
    """Apply a project type template to a project, creating its workflows."""
    ids = await project_type_service.apply_project_type(slug, type_id, body.config)
    if not ids:
        raise HTTPException(status_code=404, detail="project_type.not_found")

    orchestrator_prompt = None
    if body.workflow_filename:
        try:
            orchestrator_prompt = project_type_service.deduce_orchestrator_prompt(
                type_id, body.workflow_filename,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))

    return {"ok": True, "workflow_ids": ids, "orchestrator_prompt": orchestrator_prompt}
