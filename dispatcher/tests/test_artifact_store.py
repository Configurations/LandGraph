"""Tests for services.artifact_store — disk persistence and DB insert."""

from __future__ import annotations

import os
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from uuid import UUID

from models.task import ArtifactEvent, Task, TaskPayload
from services.artifact_store import ArtifactStore


TASK_ID = UUID("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")


@pytest.fixture
def task():
    return Task(
        task_id=TASK_ID,
        agent_id="architect",
        team_id="team1",
        thread_id="thread-42",
        phase="design",
        iteration=2,
        payload=TaskPayload(instruction="Design the system"),
        project_slug="perf-tracker",
    )


@pytest.fixture
def artifact_event():
    return ArtifactEvent(
        task_id=str(TASK_ID),
        key="architecture",
        content="# Architecture\n\nMicroservices",
        deliverable_type="document",
    )


@pytest.fixture
def store(mock_pool):
    return ArtifactStore(pool=mock_pool)


# ── _resolve_path ────────────────────────────────────


class TestResolvePath:
    def test_path_structure(self, store, task, artifact_event):
        path = store._resolve_path(task, artifact_event, workflow="main")
        # Should contain: ag_flow_root/projects/slug/team/workflow/iter:phase/agent/key.md
        assert "projects" in path
        assert "perf-tracker" in path
        assert "team1" in path
        assert "main" in path
        assert "2:design" in path
        assert "architect" in path
        assert path.endswith("architecture.md")

    def test_md_extension_not_doubled(self, store, task):
        artifact = ArtifactEvent(
            task_id=str(TASK_ID), key="notes.md", content="x", deliverable_type="doc"
        )
        path = store._resolve_path(task, artifact, workflow="main")
        assert path.endswith("notes.md")
        assert not path.endswith(".md.md")

    def test_default_slug_when_none(self, store, artifact_event):
        task = Task(
            task_id=TASK_ID,
            agent_id="dev",
            team_id="team1",
            thread_id="t",
            phase="build",
            iteration=1,
            payload=TaskPayload(instruction="x"),
            project_slug=None,
        )
        path = store._resolve_path(task, artifact_event, workflow="main")
        assert "default" in path

    def test_default_phase_when_none(self, store, artifact_event):
        task = Task(
            task_id=TASK_ID,
            agent_id="dev",
            team_id="team1",
            thread_id="t",
            phase=None,
            iteration=None,
            payload=TaskPayload(instruction="x"),
        )
        path = store._resolve_path(task, artifact_event, workflow="main")
        assert "unknown" in path
        assert "1:" in path  # iteration defaults to 1


# ── _write_file ──────────────────────────────────────


class TestWriteFile:
    def test_creates_file_and_dirs(self, store, tmp_path):
        file_path = str(tmp_path / "sub" / "dir" / "test.md")
        store._write_file(file_path, "Hello World")
        assert os.path.exists(file_path)
        with open(file_path, "r", encoding="utf-8") as f:
            assert f.read() == "Hello World"


# ── persist ──────────────────────────────────────────


class TestPersist:
    @pytest.mark.asyncio
    async def test_persist_writes_file_and_inserts_db(self, store, task, artifact_event, mock_pool, tmp_path):
        with patch.object(store, "_write_file") as mock_write, \
             patch.object(store, "_resolve_path", return_value=str(tmp_path / "out.md")):
            result = await store.persist(task, artifact_event, workflow="main")

            mock_write.assert_called_once_with(
                str(tmp_path / "out.md"),
                artifact_event.content,
            )
            mock_pool.execute.assert_called_once()
            # Check the SQL includes the right table
            sql = mock_pool.execute.call_args[0][0]
            assert "dispatcher_task_artifacts" in sql
            # Check returned path
            assert result == str(tmp_path / "out.md")

    @pytest.mark.asyncio
    async def test_persist_passes_correct_args_to_db(self, store, task, artifact_event, mock_pool):
        with patch.object(store, "_write_file"), \
             patch.object(store, "_resolve_path", return_value="/fake/path.md"):
            await store.persist(task, artifact_event, workflow="main")

            args = mock_pool.execute.call_args[0]
            assert args[1] == TASK_ID          # task_id
            assert args[2] == "architecture"   # key
            assert args[3] == "document"       # deliverable_type
            assert args[4] == "/fake/path.md"  # file_path
