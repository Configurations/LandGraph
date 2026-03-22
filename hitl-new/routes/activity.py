"""Activity timeline routes — merged PM + agent activity."""

from __future__ import annotations

import structlog
from fastapi import APIRouter, Depends, Query

from core.security import TokenData, get_current_user
from schemas.inbox import ActivityEntry, MergedActivityResponse
from services import activity_service

log = structlog.get_logger(__name__)

router = APIRouter(prefix="/api/pm", tags=["pm-activity"])


@router.get(
    "/projects/{project_id}/activity",
    response_model=MergedActivityResponse,
)
async def get_project_activity(
    project_id: int,
    team_id: str = Query(...),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    user: TokenData = Depends(get_current_user),
) -> MergedActivityResponse:
    """Get merged activity timeline for a project."""
    entries = await activity_service.get_merged_activity(
        project_id, team_id, limit,
    )
    return MergedActivityResponse(entries=entries)
