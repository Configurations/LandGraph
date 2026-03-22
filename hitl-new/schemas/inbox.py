"""Inbox and activity Pydantic v2 schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class NotificationResponse(BaseModel):
    """A single inbox notification."""

    id: int
    user_email: str
    type: str
    text: str
    issue_id: Optional[str] = None
    related_issue_id: Optional[str] = None
    relation_type: Optional[str] = None
    avatar: Optional[str] = None
    read: bool = False
    created_at: datetime


class ActivityEntry(BaseModel):
    """A single activity log entry."""

    id: int
    project_id: Optional[int] = None
    user_name: str
    action: str
    issue_id: Optional[str] = None
    detail: Optional[str] = None
    created_at: datetime
    source: str = "pm"


class MergedActivityResponse(BaseModel):
    """Merged activity from PM and agents."""

    entries: list[ActivityEntry] = Field(default_factory=list)
