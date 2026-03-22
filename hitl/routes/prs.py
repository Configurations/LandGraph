"""Pull request routes — CRUD, merge."""

from __future__ import annotations

from typing import Optional

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query

from core.security import TokenData, get_current_user
from schemas.pr import PRCreate, PRResponse, PRStatusUpdate
from services import pr_service

log = structlog.get_logger(__name__)

router = APIRouter(prefix="/api/pm", tags=["pm-reviews"])


@router.get("/reviews", response_model=list[PRResponse])
async def list_prs(
    project_slug: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    user: TokenData = Depends(get_current_user),
) -> list[PRResponse]:
    """List pull requests with optional filters."""
    return await pr_service.list_prs(
        project_slug=project_slug,
        status=status,
        limit=limit,
        offset=offset,
    )


@router.post("/reviews", response_model=PRResponse, status_code=201)
async def create_pr(
    body: PRCreate,
    user: TokenData = Depends(get_current_user),
) -> PRResponse:
    """Create a new pull request."""
    return await pr_service.create_pr(body, user.email)


@router.get("/reviews/{pr_id}", response_model=PRResponse)
async def get_pr(
    pr_id: str,
    user: TokenData = Depends(get_current_user),
) -> PRResponse:
    """Get a pull request by ID."""
    result = await pr_service.get_pr(pr_id)
    if result is None:
        raise HTTPException(status_code=404, detail="pr.not_found")
    return result


@router.put("/reviews/{pr_id}", response_model=PRResponse)
async def update_pr_status(
    pr_id: str,
    body: PRStatusUpdate,
    user: TokenData = Depends(get_current_user),
) -> PRResponse:
    """Update the status of a pull request."""
    result = await pr_service.update_status(pr_id, body, user.email)
    if result is None:
        raise HTTPException(status_code=404, detail="pr.not_found")
    return result


@router.post("/reviews/{pr_id}/merge", response_model=PRResponse)
async def merge_pr(
    pr_id: str,
    user: TokenData = Depends(get_current_user),
) -> PRResponse:
    """Merge a pull request."""
    result = await pr_service.merge_pr(pr_id, user.email)
    if result is None:
        raise HTTPException(status_code=404, detail="pr.merge_failed")
    return result
