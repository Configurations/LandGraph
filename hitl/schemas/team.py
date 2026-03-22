"""Team-related Pydantic v2 schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel


class TeamResponse(BaseModel):
    """A team with its member count."""

    id: str
    name: str
    directory: str
    member_count: int


class TeamMemberResponse(BaseModel):
    """A team member with global + team role."""

    user_id: UUID
    email: str
    display_name: str
    role_global: str
    role_team: str
    is_active: bool
    last_login: Optional[datetime] = None


class InviteRequest(BaseModel):
    """Invite a user to a team."""

    email: str
    display_name: str = ""
    role: str = "member"
