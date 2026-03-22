"""HITL routes — questions, answers, stats."""

from __future__ import annotations

from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query

from core.security import TokenData, get_current_user
from schemas.common import SuccessResponse
from schemas.hitl import AnswerRequest, QuestionResponse, StatsResponse
from services import hitl_service

router = APIRouter(prefix="/api", tags=["hitl"])


def _check_team_access(user: TokenData, team_id: str) -> None:
    """Raise 403 if user has no access to the team."""
    if user.role == "admin":
        return
    if team_id not in user.teams:
        raise HTTPException(status_code=403, detail="team.access_denied")


@router.get(
    "/teams/{team_id}/questions",
    response_model=list[QuestionResponse],
)
async def list_questions(
    team_id: str,
    status: Optional[str] = Query(None),
    channel: Optional[str] = Query(None),
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    user: TokenData = Depends(get_current_user),
) -> list[QuestionResponse]:
    """List HITL questions for a team."""
    _check_team_access(user, team_id)
    return await hitl_service.list_questions(
        team_id, status, channel, offset, limit,
    )


@router.get(
    "/teams/{team_id}/questions/stats",
    response_model=StatsResponse,
)
async def get_stats(
    team_id: str,
    user: TokenData = Depends(get_current_user),
) -> StatsResponse:
    """Get HITL request statistics for a team."""
    _check_team_access(user, team_id)
    return await hitl_service.get_stats(team_id)


@router.get("/questions/{question_id}", response_model=QuestionResponse)
async def get_question(
    question_id: UUID,
    user: TokenData = Depends(get_current_user),
) -> QuestionResponse:
    """Get a single HITL question."""
    return await hitl_service.get_question(question_id)


@router.post("/questions/{question_id}/answer", response_model=SuccessResponse)
async def answer_question(
    question_id: UUID,
    req: AnswerRequest,
    user: TokenData = Depends(get_current_user),
) -> SuccessResponse:
    """Answer, approve, or reject a HITL question."""
    return await hitl_service.answer_question(
        question_id, req.response, req.action, user.email,
    )
