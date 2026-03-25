"""Issue routes — CRUD, search, bulk create."""

from __future__ import annotations

from typing import Optional

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query

from core.security import TokenData, get_current_user
from schemas.issue import (
    IssueBulkCreate,
    IssueCreate,
    IssueDetail,
    IssueResponse,
    IssueUpdate,
)
from services import issue_service

log = structlog.get_logger(__name__)

router = APIRouter(prefix="/api/pm", tags=["pm-issues"])


@router.get("/issues", response_model=list[IssueResponse])
async def list_issues(
    team_id: Optional[str] = Query(None),
    project_id: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    assignee: Optional[str] = Query(None),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    user: TokenData = Depends(get_current_user),
) -> list[IssueResponse]:
    """List issues with optional filters. project_id accepts slug or numeric ID."""
    resolved_pid: Optional[int] = None
    if project_id is not None:
        try:
            resolved_pid = int(project_id)
        except ValueError:
            # It's a slug — resolve to integer ID
            from core.database import fetch_one
            row = await fetch_one(
                "SELECT id FROM project.pm_projects WHERE slug = $1", project_id,
            )
            resolved_pid = row["id"] if row else None
    return await issue_service.list_issues(
        team_id=team_id,
        project_id=resolved_pid,
        status=status,
        assignee=assignee,
        limit=limit,
        offset=offset,
    )


@router.post("/issues", response_model=IssueResponse, status_code=201)
async def create_issue(
    body: IssueCreate,
    team_id: str = Query(...),
    user: TokenData = Depends(get_current_user),
) -> IssueResponse:
    """Create a new issue."""
    return await issue_service.create_issue(body, team_id, user.email)


@router.get("/issues/search", response_model=list[IssueResponse])
async def search_issues(
    q: str = Query(..., min_length=1),
    team_id: str = Query(...),
    limit: int = Query(50, ge=1, le=200),
    user: TokenData = Depends(get_current_user),
) -> list[IssueResponse]:
    """Search issues by ID or title."""
    return await issue_service.search_issues(team_id, q, limit)


@router.get("/issues/{issue_id}", response_model=IssueDetail)
async def get_issue(
    issue_id: str,
    user: TokenData = Depends(get_current_user),
) -> IssueDetail:
    """Get issue detail with relations."""
    result = await issue_service.get_issue(issue_id)
    if result is None:
        raise HTTPException(status_code=404, detail="issue.not_found")
    return result


@router.put("/issues/{issue_id}", response_model=IssueResponse)
async def update_issue(
    issue_id: str,
    body: IssueUpdate,
    user: TokenData = Depends(get_current_user),
) -> IssueResponse:
    """Update an issue."""
    result = await issue_service.update_issue(issue_id, body, user.email)
    if result is None:
        raise HTTPException(status_code=404, detail="issue.not_found")
    return result


@router.delete("/issues/{issue_id}")
async def delete_issue(
    issue_id: str,
    user: TokenData = Depends(get_current_user),
) -> dict:
    """Delete an issue."""
    ok = await issue_service.delete_issue(issue_id, user.email)
    if not ok:
        raise HTTPException(status_code=404, detail="issue.not_found")
    return {"ok": True}


@router.post("/issues/bulk", response_model=list[IssueResponse], status_code=201)
async def bulk_create_issues(
    body: IssueBulkCreate,
    team_id: str = Query(...),
    user: TokenData = Depends(get_current_user),
) -> list[IssueResponse]:
    """Bulk-create issues for a project."""
    return await issue_service.bulk_create(
        body.issues, body.project_id, team_id, user.email,
    )
