"""Project-related Pydantic v2 schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, model_validator


class GitConfig(BaseModel):
    """Git connection configuration."""

    service: str
    url: str = ""
    login: str = ""
    token: str = ""
    repo_name: str = ""


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
    git_config: Optional[GitConfig] = None

    @model_validator(mode="before")
    @classmethod
    def flatten_git_config(cls, values: Any) -> Any:
        """Accept nested git_config from frontend and flatten to top-level fields."""
        if not isinstance(values, dict):
            return values
        gc = values.get("git_config")
        if gc and isinstance(gc, dict):
            values.setdefault("git_service", gc.get("service", "other"))
            values.setdefault("git_url", gc.get("url", ""))
            values.setdefault("git_login", gc.get("login", ""))
            values.setdefault("git_token", gc.get("token", ""))
            values.setdefault("git_repo_name", gc.get("repo_name", ""))
        return values


class ProjectResponse(BaseModel):
    """Public project representation."""

    id: str
    name: str
    slug: str
    team_id: str
    language: str
    git_service: str
    git_url: str
    git_login: str
    git_repo_name: str
    git_connected: bool
    git_repo_exists: bool
    wizard_pending: bool = False
    status: str
    color: str
    created_at: datetime
    updated_at: datetime


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
