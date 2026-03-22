"""Pydantic v2 schemas for request/response validation."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel, Field


# ── Request schemas ─────────────────────────────────


class TaskPayloadSchema(BaseModel):
    instruction: str
    context: dict[str, Any] = Field(default_factory=dict)
    previous_answers: list[dict[str, str]] = Field(default_factory=list)


class RunTaskRequest(BaseModel):
    agent_id: str
    team_id: str
    thread_id: str
    project_slug: Optional[str] = None
    phase: str = "build"
    iteration: int = 1
    payload: TaskPayloadSchema
    timeout_seconds: int = 300
    docker_image: Optional[str] = None


# ── Response schemas ────────────────────────────────


class TaskResponse(BaseModel):
    task_id: UUID
    status: str
    agent_id: str
    team_id: str
    project_slug: Optional[str] = None
    phase: str
    cost_usd: float = 0.0
    created_at: Optional[datetime] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    error_message: Optional[str] = None


class TaskEventResponse(BaseModel):
    id: int
    task_id: UUID
    event_type: str
    data: Any
    created_at: datetime


class TaskArtifactResponse(BaseModel):
    id: int
    task_id: UUID
    key: str
    deliverable_type: str
    file_path: Optional[str] = None
    git_branch: Optional[str] = None
    category: Optional[str] = None
    status: str = "pending"
    created_at: datetime


class TaskDetailResponse(TaskResponse):
    events: list[TaskEventResponse] = Field(default_factory=list)
    artifacts: list[TaskArtifactResponse] = Field(default_factory=list)


class CostSummaryResponse(BaseModel):
    project_slug: str
    team_id: str
    phase: str
    agent_id: str
    total_cost_usd: float
    task_count: int
    avg_cost_per_task: float


class ProjectCostsResponse(BaseModel):
    project_slug: str
    total_cost_usd: float
    by_phase: list[CostSummaryResponse]
