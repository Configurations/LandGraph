"""Project type template routes."""

from __future__ import annotations

import structlog
from fastapi import APIRouter, Depends, HTTPException

from core.security import TokenData, get_current_user
from schemas.project_type import ApplyProjectTypeRequest, ProjectTypeResponse
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
    return {"ok": True, "workflow_ids": ids}
