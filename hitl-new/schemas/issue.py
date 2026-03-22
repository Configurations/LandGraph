"""Issue-related Pydantic v2 schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class IssueCreate(BaseModel):
    """Create a new issue."""

    title: str
    description: str = ""
    priority: int = Field(default=3, ge=1, le=4)
    status: str = "todo"
    assignee: Optional[str] = None
    tags: list[str] = Field(default_factory=list)
    project_id: Optional[int] = None
    phase: Optional[str] = None


class IssueUpdate(BaseModel):
    """Partial update for an issue."""

    title: Optional[str] = None
    description: Optional[str] = None
    priority: Optional[int] = Field(default=None, ge=1, le=4)
    status: Optional[str] = None
    assignee: Optional[str] = None
    tags: Optional[list[str]] = None
    phase: Optional[str] = None


class IssueResponse(BaseModel):
    """Public issue representation."""

    id: str
    project_id: Optional[int] = None
    title: str
    description: str = ""
    status: str = "backlog"
    priority: int = 3
    assignee: Optional[str] = None
    team_id: str = ""
    tags: list[str] = Field(default_factory=list)
    phase: Optional[str] = None
    created_by: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    is_blocked: bool = False
    blocking_count: int = 0
    blocked_by_count: int = 0


class RelationResponse(BaseModel):
    """A relation from the perspective of a given issue."""

    id: int
    type: str
    direction: str
    display_type: str
    issue_id: str
    issue_title: str = ""
    issue_status: str = ""
    reason: str = ""
    created_by: Optional[str] = None
    created_at: datetime


class IssueDetail(IssueResponse):
    """Extended issue with relations and project name."""

    relations: list[RelationResponse] = Field(default_factory=list)
    project_name: Optional[str] = None


class IssueBulkCreate(BaseModel):
    """Bulk-create issues for a project."""

    issues: list[IssueCreate]
    project_id: int
