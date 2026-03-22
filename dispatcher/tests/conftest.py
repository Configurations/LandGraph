"""Shared fixtures for dispatcher tests."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest

# Ensure dispatcher package is importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


# ── Fake asyncpg record ─────────────────────────────


class FakeRecord(dict):
    """Dict subclass that supports attribute-style access like asyncpg.Record."""

    def __getitem__(self, key):
        if isinstance(key, str):
            return super().__getitem__(key)
        return super().__getitem__(key)


def make_record(**kwargs) -> FakeRecord:
    return FakeRecord(**kwargs)


# ── Mock pool ────────────────────────────────────────


@pytest.fixture
def mock_pool() -> AsyncMock:
    """An AsyncMock that behaves like asyncpg.Pool."""
    pool = AsyncMock()
    pool.execute = AsyncMock(return_value="INSERT 0 1")
    pool.fetch = AsyncMock(return_value=[])
    pool.fetchrow = AsyncMock(return_value=None)
    pool.fetchval = AsyncMock(return_value=1)

    # Support `async with pool.acquire() as conn:`
    conn = AsyncMock()
    conn.fetchval = AsyncMock(return_value=1)
    ctx = AsyncMock()
    ctx.__aenter__ = AsyncMock(return_value=conn)
    ctx.__aexit__ = AsyncMock(return_value=False)
    pool.acquire = MagicMock(return_value=ctx)

    return pool


# ── Mock Docker manager ──────────────────────────────


@pytest.fixture
def mock_docker() -> AsyncMock:
    """An AsyncMock DockerManager."""
    docker = AsyncMock()
    docker.create_container = AsyncMock(return_value="abc123container")
    docker.start_container = AsyncMock()
    docker.attach_stdin = AsyncMock(return_value=AsyncMock())
    docker.read_stdout = AsyncMock()
    docker.stop_container = AsyncMock()
    docker.remove_container = AsyncMock()
    docker.get_logs = AsyncMock(return_value="")
    docker.wait_container = AsyncMock(return_value=0)
    return docker


# ── Sample task data ─────────────────────────────────


SAMPLE_TASK_ID = UUID("12345678-1234-1234-1234-123456789abc")


@pytest.fixture
def sample_task_id() -> UUID:
    return SAMPLE_TASK_ID


@pytest.fixture
def sample_task():
    """A ready-made Task instance for tests."""
    from models.task import Task, TaskPayload

    return Task(
        task_id=SAMPLE_TASK_ID,
        agent_id="lead_dev",
        team_id="team1",
        thread_id="thread-001",
        phase="build",
        iteration=1,
        payload=TaskPayload(
            instruction="Write unit tests",
            context={"project": "demo"},
            previous_answers=[],
        ),
        timeout_seconds=300,
        project_slug="perf-tracker",
    )


@pytest.fixture
def run_task_request_dict() -> dict[str, Any]:
    """Raw dict matching RunTaskRequest shape."""
    return {
        "agent_id": "lead_dev",
        "team_id": "team1",
        "thread_id": "thread-001",
        "project_slug": "perf-tracker",
        "phase": "build",
        "iteration": 1,
        "payload": {
            "instruction": "Write unit tests",
            "context": {"project": "demo"},
            "previous_answers": [],
        },
        "timeout_seconds": 300,
    }
