"""Project type / template Pydantic v2 schemas."""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class WorkflowTemplate(BaseModel):
    """A workflow definition within a project type."""

    name: str
    filename: str
    type: str = "custom"
    mode: str = "sequential"
    priority: int = 50
    depends_on: Optional[str] = None


class ProjectTypeResponse(BaseModel):
    """A project type read from Shared/Projects/*/project.json."""

    id: str
    name: str
    description: str = ""
    team: str = ""
    workflows: list[WorkflowTemplate] = Field(default_factory=list)


class ApplyProjectTypeRequest(BaseModel):
    """Request body when applying a project type to a project."""

    config: dict[str, str] = Field(default_factory=dict)
