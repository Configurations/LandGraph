"""Task runner: full lifecycle orchestration of an agent task."""

from __future__ import annotations

import asyncio
import logging
from typing import Optional
from uuid import UUID

import asyncpg

from core.config import settings
from core.events import pg_notify
from models.task import (
    ArtifactEvent,
    ProgressEvent,
    QuestionEvent,
    ResultEvent,
    Task,
    TaskEvent,
    TaskStatus,
)
from models.schemas import RunTaskRequest
from services.artifact_store import ArtifactStore
from services.cost_tracker import CostTracker
from services.docker_manager import DockerManager
from services.hitl_bridge import HitlBridge
from services.stdio_bridge import parse_event_line, write_answer_json, write_task_json
from services.task_db import (
    build_env,
    build_task,
    build_volumes,
    fetch_task,
    insert_task,
    mark_status,
    store_event,
)

log = logging.getLogger(__name__)


class TaskRunner:
    """Orchestrates the full lifecycle of a single agent task."""

    def __init__(
        self,
        pool: asyncpg.Pool,
        docker: DockerManager,
        hitl: HitlBridge,
        artifacts: ArtifactStore,
        costs: CostTracker,
    ) -> None:
        self._pool = pool
        self._docker = docker
        self._hitl = hitl
        self._artifacts = artifacts
        self._costs = costs

    async def create(self, req: RunTaskRequest) -> UUID:
        """Create task in DB without executing. Returns task_id."""
        task = build_task(req)
        await insert_task(self._pool, task)
        log.info("Task created", extra={"task_id": str(task.task_id), "agent_id": task.agent_id})
        return task.task_id

    async def execute_by_id(self, task_id: UUID) -> None:
        """Execute a previously created task by its ID."""
        task = await fetch_task(self._pool, task_id)
        if not task:
            log.error("Task not found for execution", extra={"task_id": str(task_id)})
            return
        try:
            await self._execute(task)
        except asyncio.TimeoutError:
            await mark_status(self._pool, task.task_id, TaskStatus.TIMEOUT, "Timeout exceeded")
        except Exception as e:
            await mark_status(self._pool, task.task_id, TaskStatus.FAILURE, str(e))
            log.exception("Task failed", extra={"task_id": str(task.task_id)})

    async def run(self, req: RunTaskRequest) -> UUID:
        """Create and execute a task. Returns the task_id."""
        task_id = await self.create(req)
        await self.execute_by_id(task_id)
        return task_id

    async def cancel(self, task_id: UUID) -> bool:
        """Cancel a running task by killing its container."""
        row = await self._pool.fetchrow(
            "SELECT container_id, status FROM project.dispatcher_tasks WHERE id = $1",
            task_id,
        )
        if not row or row["status"] not in ("running", "waiting_hitl", "pending"):
            return False
        cid = row["container_id"]
        if cid:
            try:
                await self._docker.stop_container(cid, timeout=5)
                await self._docker.remove_container(cid)
            except Exception as e:
                log.warning("Error cancelling container", extra={"error": str(e)})
        await mark_status(self._pool, task_id, TaskStatus.CANCELLED)
        return True

    # ── Internal ────────────────────────────────────

    async def _execute(self, task: Task) -> None:
        """Run the container, bridge stdio, process events."""
        image = task.docker_image or settings.agent_default_image
        env = build_env(task)
        volumes = build_volumes(task)

        # Connect to Docker network if the task needs RAG access
        network = None
        if task.payload.context.get("rag_endpoint"):
            network = "langgraph-net"

        async with self._docker.managed_container(
            image=image, env=env, volumes=volumes,
            mem_limit=settings.agent_mem_limit,
            cpu_quota=settings.agent_cpu_quota,
            name=f"agent-{task.agent_id}-{str(task.task_id)[:8]}",
            network=network,
        ) as container_id:
            task.container_id = container_id
            await self._pool.execute(
                """UPDATE project.dispatcher_tasks
                   SET container_id=$1, status='running', started_at=NOW()
                   WHERE id=$2""",
                container_id, task.task_id,
            )
            await self._docker.start_container(container_id)
            ws = await self._docker.attach_stdin(container_id)
            await write_task_json(ws, task.to_stdin_dict())
            await asyncio.wait_for(
                self._process_stdout(task, container_id, ws),
                timeout=float(task.timeout_seconds),
            )
            stderr_logs = await self._docker.get_logs(container_id)
            if stderr_logs:
                await store_event(self._pool, task.task_id, "progress", {"stderr": stderr_logs[:4000]})

    async def _process_stdout(self, task: Task, container_id: str, ws) -> None:
        """Read stdout line by line until result event."""
        async for raw in self._docker.read_stdout(container_id):
            text = raw.decode("utf-8", errors="replace") if isinstance(raw, bytes) else raw
            for line in text.splitlines():
                event = parse_event_line(line)
                if event is None:
                    continue
                await self._handle_event(task, event, ws)
                if isinstance(event, ResultEvent):
                    return

    async def _handle_event(self, task: Task, event: TaskEvent, ws) -> None:
        """Dispatch a single event."""
        if isinstance(event, ProgressEvent):
            await store_event(self._pool, task.task_id, "progress", event.data)
            await pg_notify(self._pool, "task_progress", {
                "task_id": str(task.task_id), "data": event.data[:500],
            })
        elif isinstance(event, ArtifactEvent):
            await store_event(self._pool, task.task_id, "artifact", {
                "key": event.key, "deliverable_type": event.deliverable_type,
            })
            await self._artifacts.persist(task, event)
            await pg_notify(self._pool, "task_artifact", {
                "task_id": str(task.task_id), "key": event.key,
            })
        elif isinstance(event, QuestionEvent):
            await store_event(self._pool, task.task_id, "question", {
                "prompt": event.prompt, "context": event.context,
            })
            await self._pool.execute(
                "UPDATE project.dispatcher_tasks SET status='waiting_hitl' WHERE id=$1",
                task.task_id,
            )
            answer = await self._hitl.ask(task, event)
            await write_answer_json(ws, str(task.task_id), answer)
            await self._pool.execute(
                "UPDATE project.dispatcher_tasks SET status='running' WHERE id=$1",
                task.task_id,
            )
        elif isinstance(event, ResultEvent):
            st = TaskStatus.SUCCESS if event.status == "success" else TaskStatus.FAILURE
            await mark_status(self._pool, task.task_id, st)
            if event.cost_usd > 0:
                await self._costs.record(
                    task.task_id, task.project_slug, task.team_id,
                    task.phase, task.agent_id, event.cost_usd,
                )
