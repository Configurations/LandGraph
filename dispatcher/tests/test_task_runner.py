"""Tests for services.task_runner — task lifecycle orchestration."""

from __future__ import annotations

import asyncio
import pytest
from unittest.mock import AsyncMock, patch
from uuid import UUID, uuid4

from models.task import (
    ArtifactEvent,
    ProgressEvent,
    QuestionEvent,
    ResultEvent,
    Task,
    TaskPayload,
    TaskStatus,
)
from models.schemas import RunTaskRequest, TaskPayloadSchema
from services.task_runner import TaskRunner
from tests.conftest import make_record


TASK_ID = UUID("99999999-8888-7777-6666-555544443333")


@pytest.fixture
def runner(mock_pool, mock_docker):
    hitl = AsyncMock()
    artifacts = AsyncMock()
    costs = AsyncMock()
    return TaskRunner(
        pool=mock_pool, docker=mock_docker,
        hitl=hitl, artifacts=artifacts, costs=costs,
    )


@pytest.fixture
def run_request():
    return RunTaskRequest(
        agent_id="lead_dev", team_id="team1", thread_id="thread-001",
        project_slug="perf-tracker", phase="build", iteration=1,
        payload=TaskPayloadSchema(instruction="Write unit tests", context={"project": "demo"}),
        timeout_seconds=300,
    )


# ── create ───────────────────────────────────────────


class TestCreate:
    @pytest.mark.asyncio
    async def test_create_returns_uuid(self, runner, run_request, mock_pool):
        task_id = await runner.create(run_request)
        assert isinstance(task_id, UUID)

    @pytest.mark.asyncio
    async def test_create_inserts_into_db(self, runner, run_request, mock_pool):
        await runner.create(run_request)
        mock_pool.execute.assert_called_once()
        sql = mock_pool.execute.call_args[0][0]
        assert "dispatcher_tasks" in sql


# ── cancel ───────────────────────────────────────────


class TestCancel:
    @pytest.mark.asyncio
    async def test_cancel_running_task(self, runner, mock_pool, mock_docker):
        mock_pool.fetchrow = AsyncMock(return_value=make_record(
            container_id="cid-123", status="running"
        ))
        result = await runner.cancel(TASK_ID)
        assert result is True
        mock_docker.stop_container.assert_called_once()

    @pytest.mark.asyncio
    async def test_cancel_completed_returns_false(self, runner, mock_pool):
        mock_pool.fetchrow = AsyncMock(return_value=make_record(
            container_id="cid", status="success"
        ))
        assert await runner.cancel(TASK_ID) is False

    @pytest.mark.asyncio
    async def test_cancel_nonexistent_returns_false(self, runner, mock_pool):
        mock_pool.fetchrow = AsyncMock(return_value=None)
        assert await runner.cancel(TASK_ID) is False

    @pytest.mark.asyncio
    async def test_cancel_tolerates_docker_error(self, runner, mock_pool, mock_docker):
        mock_pool.fetchrow = AsyncMock(return_value=make_record(
            container_id="cid", status="running"
        ))
        mock_docker.stop_container = AsyncMock(side_effect=RuntimeError("gone"))
        assert await runner.cancel(TASK_ID) is True


# ── _handle_event ────────────────────────────────────


class TestHandleEvent:
    @pytest.mark.asyncio
    async def test_progress_event(self, runner, sample_task, mock_pool):
        event = ProgressEvent(task_id=str(TASK_ID), data="Step 1 done")
        with patch("services.task_runner.store_event", new_callable=AsyncMock), \
             patch("services.task_runner.pg_notify", new_callable=AsyncMock) as mock_notify:
            await runner._handle_event(sample_task, event, AsyncMock())
        mock_notify.assert_called_once()

    @pytest.mark.asyncio
    async def test_artifact_event_persists(self, runner, sample_task, mock_pool):
        event = ArtifactEvent(task_id=str(TASK_ID), key="prd", content="c", deliverable_type="doc")
        with patch("services.task_runner.store_event", new_callable=AsyncMock), \
             patch("services.task_runner.pg_notify", new_callable=AsyncMock):
            await runner._handle_event(sample_task, event, AsyncMock())
        runner._artifacts.persist.assert_called_once()

    @pytest.mark.asyncio
    async def test_question_event_asks_hitl(self, runner, sample_task, mock_pool):
        event = QuestionEvent(task_id=str(TASK_ID), prompt="Confirm?")
        runner._hitl.ask = AsyncMock(return_value="Yes")
        with patch("services.task_runner.store_event", new_callable=AsyncMock):
            await runner._handle_event(sample_task, event, AsyncMock())
        runner._hitl.ask.assert_called_once()

    @pytest.mark.asyncio
    async def test_result_event_records_cost(self, runner, sample_task, mock_pool):
        event = ResultEvent(task_id=str(TASK_ID), status="success", cost_usd=0.1)
        with patch("services.task_runner.mark_status", new_callable=AsyncMock):
            await runner._handle_event(sample_task, event, AsyncMock())
        runner._costs.record.assert_called_once()

    @pytest.mark.asyncio
    async def test_result_failure_no_cost(self, runner, sample_task, mock_pool):
        event = ResultEvent(task_id=str(TASK_ID), status="failure", cost_usd=0.0)
        with patch("services.task_runner.mark_status", new_callable=AsyncMock):
            await runner._handle_event(sample_task, event, AsyncMock())
        runner._costs.record.assert_not_called()


# ── execute_by_id ────────────────────────────────────


class TestExecuteById:
    @pytest.mark.asyncio
    async def test_not_found(self, runner, mock_pool):
        with patch("services.task_runner.fetch_task", new_callable=AsyncMock, return_value=None):
            await runner.execute_by_id(TASK_ID)

    @pytest.mark.asyncio
    async def test_timeout_marks_task(self, runner, mock_pool):
        task = Task(
            task_id=TASK_ID, agent_id="dev", team_id="t1", thread_id="th1",
            phase="build", iteration=1, payload=TaskPayload(instruction="x"),
        )
        with patch("services.task_runner.fetch_task", new_callable=AsyncMock, return_value=task), \
             patch.object(runner, "_execute", new_callable=AsyncMock, side_effect=asyncio.TimeoutError()), \
             patch("services.task_runner.mark_status", new_callable=AsyncMock) as mock_mark:
            await runner.execute_by_id(TASK_ID)
            mock_mark.assert_called_once()

    @pytest.mark.asyncio
    async def test_exception_marks_failure(self, runner, mock_pool):
        task = Task(
            task_id=TASK_ID, agent_id="dev", team_id="t1", thread_id="th1",
            phase="build", iteration=1, payload=TaskPayload(instruction="x"),
        )
        with patch("services.task_runner.fetch_task", new_callable=AsyncMock, return_value=task), \
             patch.object(runner, "_execute", new_callable=AsyncMock, side_effect=RuntimeError("crash")), \
             patch("services.task_runner.mark_status", new_callable=AsyncMock) as mock_mark:
            await runner.execute_by_id(TASK_ID)
            mock_mark.assert_called_once()


# ── run ──────────────────────────────────────────────


class TestRun:
    @pytest.mark.asyncio
    async def test_run_creates_and_executes(self, runner, run_request):
        with patch.object(runner, "create", new_callable=AsyncMock, return_value=TASK_ID), \
             patch.object(runner, "execute_by_id", new_callable=AsyncMock) as mock_exec:
            result = await runner.run(run_request)
            assert result == TASK_ID
            mock_exec.assert_called_once_with(TASK_ID)
