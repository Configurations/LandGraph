"""Workflow visualization Pydantic v2 schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class PhaseAgent(BaseModel):
    """An agent participating in a workflow phase."""

    agent_id: str
    name: str = ""
    status: str = "pending"
    task_id: Optional[str] = None


class PhaseDeliverable(BaseModel):
    """A deliverable expected from a workflow phase."""

    key: str
    agent_id: str
    deliverable_type: str = ""
    category: Optional[str] = None
    required: bool = True
    status: str = "pending"
    artifact_id: Optional[int] = None


class PhaseStatus(BaseModel):
    """Status of a single workflow phase."""

    id: str
    name: str
    status: str = "pending"
    agents: list[PhaseAgent] = Field(default_factory=list)
    deliverables: list[PhaseDeliverable] = Field(default_factory=list)


class WorkflowStatusResponse(BaseModel):
    """Full workflow status across all phases."""

    phases: list[PhaseStatus] = Field(default_factory=list)
    current_phase: Optional[str] = None
    total_phases: int = 0
    completed_phases: int = 0


# ── Multi-workflow schemas ─────────────────────────


class ProjectWorkflowCreate(BaseModel):
    """Request body for creating a project workflow."""

    workflow_name: str
    workflow_type: str = "custom"
    workflow_json_path: str
    mode: str = "sequential"
    priority: int = 50
    depends_on_workflow_id: Optional[int] = None
    config: dict[str, str] = Field(default_factory=dict)


class ProjectWorkflowResponse(BaseModel):
    """A project workflow record."""

    id: int
    project_slug: str
    workflow_name: str
    workflow_type: str
    workflow_json_path: str
    status: str
    mode: str
    priority: int
    iteration: int
    depends_on_workflow_id: Optional[int] = None
    config: dict[str, str] = Field(default_factory=dict)
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    created_at: Optional[str] = None


class DeliverableWithContent(BaseModel):
    """Deliverable with full markdown content for inline preview."""

    id: int
    key: str
    agent_id: str
    agent_name: str = ""
    status: str
    version: int = 1
    file_path: Optional[str] = None
    content: str = ""
    reviewer: Optional[str] = None
    review_comment: Optional[str] = None
    reviewed_at: Optional[str] = None
    created_at: Optional[str] = None


class PhaseDetailResponse(BaseModel):
    """A single phase/group with its deliverables including content."""

    id: int
    phase_key: str
    phase_name: str
    group_key: str
    status: str
    deliverables: list[DeliverableWithContent] = []


class WorkflowPhasesResponse(BaseModel):
    """Full workflow execution state with phases and deliverables."""

    workflow_id: int
    workflow_name: str
    status: str
    human_gate: Optional[dict] = None
    phases: list[PhaseDetailResponse] = []
