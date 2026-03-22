"""Dashboard routes — active tasks, costs, overview."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from core.security import TokenData, get_current_user
from services import dashboard_service

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


@router.get("/active-tasks")
async def active_tasks(
    team_id: Optional[str] = Query(None),
    user: TokenData = Depends(get_current_user),
) -> list[dict]:
    """Get active tasks, optionally filtered by team."""
    return await dashboard_service.get_active_tasks(team_id)


@router.get("/costs/{slug}")
async def project_costs(
    slug: str,
    user: TokenData = Depends(get_current_user),
) -> dict:
    """Get cost breakdown for a project."""
    result = await dashboard_service.get_project_costs(slug)
    if result is None:
        raise HTTPException(status_code=404, detail="dashboard.costs_unavailable")
    return result


@router.get("/overview")
async def overview(
    team_id: Optional[str] = Query(None),
    user: TokenData = Depends(get_current_user),
) -> dict:
    """Get dashboard overview metrics."""
    return await dashboard_service.get_overview(team_id, user.teams)
