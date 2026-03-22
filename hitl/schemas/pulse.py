"""Pulse metrics Pydantic v2 schemas."""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class MetricValue(BaseModel):
    """A single metric with label and sublabel."""

    value: str
    sub: str = ""


class TeamMemberActivity(BaseModel):
    """Activity breakdown for a single team member."""

    name: str
    total: int = 0
    completed: int = 0
    active: int = 0


class DependencyHealth(BaseModel):
    """Dependency health metrics across issues."""

    blocked: int = 0
    blocking: int = 0
    chains: int = 0
    bottlenecks: list[dict] = Field(default_factory=list)


class BurndownPoint(BaseModel):
    """A single point on the burndown chart."""

    date: str
    remaining: int = 0
    completed: int = 0


class PulseResponse(BaseModel):
    """Full pulse dashboard response."""

    status_distribution: dict[str, int] = Field(default_factory=dict)
    team_activity: list[TeamMemberActivity] = Field(default_factory=list)
    dependency_health: DependencyHealth = Field(default_factory=DependencyHealth)
    velocity: MetricValue = Field(default_factory=lambda: MetricValue(value="0", sub=""))
    throughput: MetricValue = Field(default_factory=lambda: MetricValue(value="0", sub=""))
    cycle_time: MetricValue = Field(default_factory=lambda: MetricValue(value="0", sub=""))
    burndown: list[BurndownPoint] = Field(default_factory=list)
