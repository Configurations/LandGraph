"""Deliverable-related Pydantic v2 schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class DeliverableResponse(BaseModel):
    """Public deliverable representation (list view)."""

    id: int
    task_id: str
    key: str
    deliverable_type: str
    file_path: Optional[str] = None
    git_branch: Optional[str] = None
    category: Optional[str] = None
    status: str = "pending"
    version: int = 1
    reviewer: Optional[str] = None
    review_comment: Optional[str] = None
    reviewed_at: Optional[datetime] = None
    created_at: datetime
    agent_id: str = ""
    phase: str = ""
    project_slug: str = ""


class DeliverableDetail(DeliverableResponse):
    """Extended deliverable with content and cost."""

    content: str = ""
    cost_usd: float = 0.0


class ValidateRequest(BaseModel):
    """Approve or reject a deliverable."""

    verdict: str
    comment: Optional[str] = None


class RemarkRequest(BaseModel):
    """Add a remark to a deliverable."""

    comment: str


class RemarkResponse(BaseModel):
    """A remark on a deliverable."""

    id: int
    artifact_id: int
    reviewer: str
    comment: str
    created_at: datetime


class UpdateContentRequest(BaseModel):
    """Update deliverable markdown content."""

    content: str


class BranchInfo(BaseModel):
    """Git branch metadata."""

    name: str
    ahead: int = 0
    behind: int = 0
    last_commit: str = ""


class BranchDiffResponse(BaseModel):
    """Diff between a branch and dev."""

    branch: str
    files: list[dict] = []
