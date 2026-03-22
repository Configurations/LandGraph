"""Pull request Pydantic v2 schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class PRCreate(BaseModel):
    """Create a new pull request."""

    branch: str
    title: str
    issue_id: Optional[str] = None
    project_slug: str = ""


class PRStatusUpdate(BaseModel):
    """Update the status of a pull request."""

    status: str
    comment: str = ""


class PRResponse(BaseModel):
    """Public pull request representation."""

    id: str
    title: str
    author: str
    issue_id: Optional[str] = None
    issue_title: Optional[str] = None
    status: str = "draft"
    additions: int = 0
    deletions: int = 0
    files: int = 0
    branch: str = ""
    remote_url: str = ""
    project_slug: str = ""
    created_at: datetime
    updated_at: datetime
    merged_by: Optional[str] = None
    merged_at: Optional[datetime] = None
