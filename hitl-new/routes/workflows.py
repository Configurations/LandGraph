"""Multi-workflow routes — CRUD and lifecycle for project workflows."""

from __future__ import annotations

from typing import Optional

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query

from core.security import TokenData, get_current_user
from schemas.workflow import (
    ProjectWorkflowCreate,
    ProjectWorkflowResponse,
)
from services import multi_workflow_service

log = structlog.get_logger(__name__)

router = APIRouter(prefix="/api/projects", tags=["workflows"])


@router.get("/{slug}/workflows", response_model=list[ProjectWorkflowResponse])
async def list_workflows(
    slug: str,
    status: Optional[str] = Query(None),
    user: TokenData = Depends(get_current_user),
) -> list[ProjectWorkflowResponse]:
    """List all workflows for a project."""
    return await multi_workflow_service.list_workflows(slug, status=status)


@router.post("/{slug}/workflows", response_model=ProjectWorkflowResponse, status_code=201)
async def create_workflow(
    slug: str,
    body: ProjectWorkflowCreate,
    user: TokenData = Depends(get_current_user),
) -> ProjectWorkflowResponse:
    """Create a new workflow for a project."""
    return await multi_workflow_service.create_workflow(slug, body)


@router.get("/{slug}/workflows/{workflow_id}", response_model=ProjectWorkflowResponse)
async def get_workflow(
    slug: str,
    workflow_id: int,
    user: TokenData = Depends(get_current_user),
) -> ProjectWorkflowResponse:
    """Get a single workflow by ID."""
    wf = await multi_workflow_service.get_workflow(workflow_id)
    if wf is None or wf.project_slug != slug:
        raise HTTPException(status_code=404, detail="workflow.not_found")
    return wf


@router.post("/{slug}/workflows/{workflow_id}/activate", response_model=ProjectWorkflowResponse)
async def activate_workflow(
    slug: str,
    workflow_id: int,
    user: TokenData = Depends(get_current_user),
) -> ProjectWorkflowResponse:
    """Activate a pending workflow."""
    wf = await multi_workflow_service.activate_workflow(workflow_id)
    if wf is None:
        raise HTTPException(status_code=409, detail="workflow.invalid_transition")
    return wf


@router.post("/{slug}/workflows/{workflow_id}/complete", response_model=ProjectWorkflowResponse)
async def complete_workflow(
    slug: str,
    workflow_id: int,
    user: TokenData = Depends(get_current_user),
) -> ProjectWorkflowResponse:
    """Mark an active workflow as completed."""
    wf = await multi_workflow_service.complete_workflow(workflow_id)
    if wf is None:
        raise HTTPException(status_code=409, detail="workflow.invalid_transition")
    return wf


@router.post("/{slug}/workflows/{workflow_id}/pause", response_model=ProjectWorkflowResponse)
async def pause_workflow(
    slug: str,
    workflow_id: int,
    user: TokenData = Depends(get_current_user),
) -> ProjectWorkflowResponse:
    """Pause an active workflow."""
    wf = await multi_workflow_service.pause_workflow(workflow_id)
    if wf is None:
        raise HTTPException(status_code=409, detail="workflow.invalid_transition")
    return wf


@router.post("/{slug}/workflows/{workflow_id}/cancel", response_model=ProjectWorkflowResponse)
async def cancel_workflow(
    slug: str,
    workflow_id: int,
    user: TokenData = Depends(get_current_user),
) -> ProjectWorkflowResponse:
    """Cancel a workflow."""
    wf = await multi_workflow_service.cancel_workflow(workflow_id)
    if wf is None:
        raise HTTPException(status_code=409, detail="workflow.invalid_transition")
    return wf


@router.post("/{slug}/workflows/{workflow_id}/relaunch", response_model=ProjectWorkflowResponse)
async def relaunch_workflow(
    slug: str,
    workflow_id: int,
    user: TokenData = Depends(get_current_user),
) -> ProjectWorkflowResponse:
    """Re-launch a completed or cancelled workflow with a new iteration."""
    wf = await multi_workflow_service.relaunch_workflow(workflow_id)
    if wf is None:
        raise HTTPException(status_code=409, detail="workflow.invalid_transition")
    return wf
