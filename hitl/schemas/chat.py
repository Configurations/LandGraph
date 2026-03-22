"""Chat and agent Pydantic v2 schemas."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class ChatMessageResponse(BaseModel):
    """A single chat message."""

    id: int
    team_id: str
    agent_id: str
    thread_id: str
    sender: str
    content: str
    created_at: datetime


class SendMessageRequest(BaseModel):
    """Send a message to an agent."""

    message: str


class AgentResponse(BaseModel):
    """Agent info with pending question count."""

    id: str
    name: str
    llm: str = ""
    type: str = "single"
    pending_questions: int = 0
