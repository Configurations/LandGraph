"""Workflow visualization routes."""

from __future__ import annotations

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query

from core.security import TokenData, get_current_user
from schemas.workflow import PhaseStatus, WorkflowStatusResponse
from services import workflow_service
from services.workflow_service import _get_project_team

log = structlog.get_logger(__name__)

router = APIRouter(prefix="/api/projects", tags=["workflow"])


@router.get("/{slug}/workflow", response_model=WorkflowStatusResponse)
async def get_workflow_status(
    slug: str,
    user: TokenData = Depends(get_current_user),
) -> WorkflowStatusResponse:
    """Get the workflow status for a project."""
    team_id = await _get_project_team(slug)
    if team_id is None:
        raise HTTPException(status_code=404, detail="project.not_found")
    return await workflow_service.get_workflow_status(slug, team_id)


@router.get("/{slug}/workflow/{phase_id}", response_model=PhaseStatus)
async def get_phase_detail(
    slug: str,
    phase_id: str,
    user: TokenData = Depends(get_current_user),
) -> PhaseStatus:
    """Get detail for a single workflow phase."""
    team_id = await _get_project_team(slug)
    if team_id is None:
        raise HTTPException(status_code=404, detail="project.not_found")
    result = await workflow_service.get_phase_detail(slug, team_id, phase_id)
    if result is None:
        raise HTTPException(status_code=404, detail="workflow.phase_not_found")
    return result
