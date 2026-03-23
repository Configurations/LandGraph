"""HITL-related Pydantic v2 schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel


class QuestionResponse(BaseModel):
    """A HITL question/approval request."""

    id: UUID
    thread_id: str
    agent_id: str
    team_id: str
    request_type: str
    prompt: str
    context: Any = None
    channel: str = ""
    status: str = "pending"
    response: Optional[str] = None
    reviewer: Optional[str] = None
    created_at: datetime
    answered_at: Optional[datetime] = None
    agent_avatar_url: Optional[str] = None


class AnswerRequest(BaseModel):
    """Answer to a HITL question."""

    response: str
    action: str = "answer"  # answer | approve | reject


class StatsResponse(BaseModel):
    """HITL request statistics for a team."""

    pending: int
    answered: int
    timeout: int
    cancelled: int
    total: int
