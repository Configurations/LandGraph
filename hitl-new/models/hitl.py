"""HITL request and chat message dataclasses (pure data, no ORM)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional
from uuid import UUID


@dataclass
class HitlRequest:
    """A human-in-the-loop request (question or approval)."""

    id: UUID
    thread_id: str
    agent_id: str
    team_id: str
    request_type: str
    prompt: str
    context: dict[str, Any]
    channel: str
    status: str
    response: Optional[str]
    reviewer: Optional[str]
    response_channel: Optional[str]
    created_at: datetime
    answered_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None


@dataclass
class ChatMessage:
    """A chat message in a team/agent/thread context."""

    id: int
    team_id: str
    agent_id: str
    thread_id: str
    sender: str
    content: str
    created_at: datetime
