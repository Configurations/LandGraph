"""Pulse metrics route."""

from __future__ import annotations

from typing import Optional

import structlog
from fastapi import APIRouter, Depends, Query

from core.security import TokenData, get_current_user
from schemas.pulse import PulseResponse
from services import pulse_service

log = structlog.get_logger(__name__)

router = APIRouter(prefix="/api/pm", tags=["pm-pulse"])


@router.get("/pulse", response_model=PulseResponse)
async def get_pulse(
    team_id: Optional[str] = Query(None),
    project_id: Optional[int] = Query(None),
    user: TokenData = Depends(get_current_user),
) -> PulseResponse:
    """Get pulse metrics for the dashboard."""
    return await pulse_service.get_pulse(
        team_id=team_id,
        project_id=project_id,
    )
