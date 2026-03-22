"""Tests for services.task_db — DB helpers and task building."""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, patch
from uuid import UUID, uuid4

from models.task import Task, TaskPayload, TaskStatus
from models.schemas import RunTaskRequest, TaskPayloadSchema
from services.task_db import build_task, build_env, build_volumes


# ── build_task ──────────────────────────────────────


class TestBuildTask:
    def test_maps_all_fields(self):
        req = RunTaskRequest(
            agent_id="lead_dev", team_id="team1", thread_id="thread-001",
            project_slug="perf-tracker", phase="build", iteration=1,
            payload=TaskPayloadSchema(instruction="Write unit tests", context={"project": "demo"}),
            timeout_seconds=300,
        )
        task = build_task(req)
        assert task.agent_id == "lead_dev"
        assert task.team_id == "team1"
        assert task.thread_id == "thread-001"
        assert task.project_slug == "perf-tracker"
        assert task.phase == "build"
        assert task.iteration == 1
        assert task.payload.instruction == "Write unit tests"
        assert task.timeout_seconds == 300

    def test_generates_unique_ids(self):
        req = RunTaskRequest(
            agent_id="dev", team_id="t", thread_id="th", phase="build",
            payload=TaskPayloadSchema(instruction="x"),
        )
        t1 = build_task(req)
        t2 = build_task(req)
        assert t1.task_id != t2.task_id


# ── build_env ───────────────────────────────────────


class TestBuildEnv:
    def test_includes_agent_role(self, sample_task):
        env = build_env(sample_task)
        assert env["AGENT_ROLE"] == "lead_dev"
        assert "ANTHROPIC_API_KEY" in env

    def test_env_uses_os_environ(self, sample_task):
        with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "sk-test", "AGENT_MAX_TURNS": "5"}):
            env = build_env(sample_task)
            assert env["ANTHROPIC_API_KEY"] == "sk-test"
            assert env["AGENT_MAX_TURNS"] == "5"


# ── build_volumes ───────────────────────────────────


class TestBuildVolumes:
    def test_maps_project_repo(self, sample_task):
        volumes = build_volumes(sample_task)
        assert len(volumes) >= 1
        assert "/workspace" in volumes[0]
        assert "perf-tracker" in volumes[0]

    def test_default_slug(self):
        task = Task(
            task_id=uuid4(), agent_id="dev", team_id="t", thread_id="th",
            phase="build", iteration=1, payload=TaskPayload(instruction="x"),
            project_slug=None,
        )
        volumes = build_volumes(task)
        assert "default" in volumes[0]
