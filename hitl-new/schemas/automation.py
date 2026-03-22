"""Automation rules Pydantic v2 schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class AutomationRuleCreate(BaseModel):
    """Create or update an automation rule."""

    project_slug: Optional[str] = None
    workflow_type: Optional[str] = None
    deliverable_type: Optional[str] = None
    auto_approve: bool = False
    confidence_threshold: float = 0.0
    min_approved_history: int = 5


class AutomationRuleResponse(BaseModel):
    """An automation rule record."""

    id: int
    project_slug: Optional[str] = None
    workflow_type: Optional[str] = None
    deliverable_type: Optional[str] = None
    auto_approve: bool = False
    confidence_threshold: float = 0.0
    min_approved_history: int = 5
    created_at: Optional[datetime] = None


class AutomationStatsResponse(BaseModel):
    """Automation statistics for a project."""

    total_reviewed: int = 0
    auto_approved: int = 0
    manual_approved: int = 0
    rejected: int = 0
    auto_pct: float = 0.0
    manual_pct: float = 0.0
    rejected_pct: float = 0.0


class AgentConfidenceResponse(BaseModel):
    """Confidence score for an agent on a deliverable type."""

    agent_id: str
    deliverable_type: str = ""
    total: int = 0
    approved: int = 0
    rejected: int = 0
    confidence: float = 0.0
