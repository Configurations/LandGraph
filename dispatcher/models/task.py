"""Task and event dataclasses for the dispatcher."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Optional
from uuid import UUID


class TaskStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    WAITING_HITL = "waiting_hitl"
    SUCCESS = "success"
    FAILURE = "failure"
    TIMEOUT = "timeout"
    CANCELLED = "cancelled"


class EventType(str, Enum):
    PROGRESS = "progress"
    ARTIFACT = "artifact"
    QUESTION = "question"
    RESULT = "result"


@dataclass
class TaskPayload:
    instruction: str
    context: dict[str, Any] = field(default_factory=dict)
    previous_answers: list[dict[str, str]] = field(default_factory=list)


@dataclass
class Task:
    task_id: UUID
    agent_id: str
    team_id: str
    thread_id: str
    phase: str
    iteration: int
    payload: TaskPayload
    timeout_seconds: int = 300
    project_slug: Optional[str] = None
    docker_image: Optional[str] = None
    container_id: Optional[str] = None
    status: TaskStatus = TaskStatus.PENDING
    cost_usd: float = 0.0
    created_at: Optional[datetime] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    error_message: Optional[str] = None

    def to_stdin_dict(self) -> dict[str, Any]:
        """Serialise for writing to container stdin."""
        return {
            "task_id": str(self.task_id),
            "agent_id": self.agent_id,
            "team_id": self.team_id,
            "thread_id": self.thread_id,
            "phase": self.phase,
            "iteration": self.iteration,
            "payload": {
                "instruction": self.payload.instruction,
                "context": self.payload.context,
                "previous_answers": self.payload.previous_answers,
            },
            "timeout_seconds": self.timeout_seconds,
        }


# ── Event types ─────────────────────────────────────


@dataclass
class ProgressEvent:
    task_id: str
    data: str


@dataclass
class ArtifactEvent:
    task_id: str
    key: str
    content: str
    deliverable_type: str


@dataclass
class QuestionEvent:
    task_id: str
    prompt: str
    context: dict[str, Any] = field(default_factory=dict)


@dataclass
class ResultEvent:
    task_id: str
    status: str  # "success" or "failure"
    exit_code: int = 0
    cost_usd: float = 0.0


TaskEvent = ProgressEvent | ArtifactEvent | QuestionEvent | ResultEvent
