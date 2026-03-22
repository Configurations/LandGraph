"""User and team membership dataclasses (pure data, no ORM)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional
from uuid import UUID


@dataclass
class User:
    """A HITL console user."""

    id: UUID
    email: str
    password_hash: Optional[str]
    display_name: str
    role: str  # 'undefined' | 'member' | 'admin'
    auth_type: str  # 'local' | 'google'
    culture: str
    is_active: bool
    created_at: datetime
    last_login: Optional[datetime] = None


@dataclass
class TeamMember:
    """A user's membership in a team."""

    id: UUID
    user_id: UUID
    team_id: str
    role: str = "member"
