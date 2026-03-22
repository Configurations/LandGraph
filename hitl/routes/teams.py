"""Team routes — list teams, members, invite."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from core.security import TokenData, get_current_user
from schemas.common import SuccessResponse
from schemas.team import InviteRequest, TeamMemberResponse, TeamResponse
from services import team_service

router = APIRouter(prefix="/api", tags=["teams"])


def _check_team_access(user: TokenData, team_id: str) -> None:
    """Raise 403 if user has no access to the team."""
    if user.role == "admin":
        return
    if team_id not in user.teams:
        raise HTTPException(status_code=403, detail="team.access_denied")


@router.get("/teams", response_model=list[TeamResponse])
async def list_teams(
    user: TokenData = Depends(get_current_user),
) -> list[TeamResponse]:
    """List teams visible to the current user."""
    return await team_service.list_teams(user.user_id, user.role)


@router.get("/teams/{team_id}/members", response_model=list[TeamMemberResponse])
async def list_members(
    team_id: str,
    user: TokenData = Depends(get_current_user),
) -> list[TeamMemberResponse]:
    """List members of a team."""
    _check_team_access(user, team_id)
    return await team_service.list_members(team_id)


@router.post("/teams/{team_id}/members", response_model=SuccessResponse)
async def invite_member(
    team_id: str,
    req: InviteRequest,
    user: TokenData = Depends(get_current_user),
) -> SuccessResponse:
    """Invite a user to a team (admin only)."""
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="common.forbidden")
    return await team_service.invite_member(
        team_id, req.email, req.display_name, req.role,
    )
