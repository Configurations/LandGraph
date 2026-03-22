"""Project-related Pydantic v2 schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class ProjectCreate(BaseModel):
    """Create a new project."""

    name: str
    slug: str
    team_id: str
    language: str = "fr"
    git_service: str = "other"
    git_url: str = ""
    git_login: str = ""
    git_token: str = ""
    git_repo_name: str = ""


class ProjectResponse(BaseModel):
    """Public project representation."""

    id: int
    name: str
    slug: str
    team_id: str
    language: str
    git_service: str
    git_url: str
    git_login: str
    git_repo_name: str
    status: str
    color: str
    created_at: datetime
    updated_at: datetime


class GitConfig(BaseModel):
    """Git connection configuration."""

    service: str
    url: str = ""
    login: str = ""
    token: str = ""
    repo_name: str = ""


class GitTestResponse(BaseModel):
    """Result of a git connection test."""

    connected: bool
    repo_exists: bool
    message: str = ""


class SlugCheckResponse(BaseModel):
    """Slug availability check result."""

    exists: bool
    path: str


class GitStatusResponse(BaseModel):
    """Git repository status."""

    branch: str
    clean: bool
    ahead: int
    behind: int
