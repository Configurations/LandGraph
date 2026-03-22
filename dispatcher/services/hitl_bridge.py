"""HITL bridge: create questions in DB, wait for human answers."""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID, uuid4

import asyncpg

from core.config import settings
from core.events import HitlResponseWaiter, pg_notify
from models.task import QuestionEvent, Task

log = logging.getLogger(__name__)


class HitlBridge:
    """Creates HITL requests and waits for responses via PG NOTIFY."""

    def __init__(self, pool: asyncpg.Pool, waiter: HitlResponseWaiter) -> None:
        self._pool = pool
        self._waiter = waiter

    async def ask(
        self,
        task: Task,
        question: QuestionEvent,
        timeout: float = 0,
    ) -> str:
        """Create a HITL request and wait for the answer.

        Returns the response text, or raises asyncio.TimeoutError.
        """
        if timeout <= 0:
            timeout = float(settings.hitl_question_timeout)

        request_id = uuid4()
        await self._insert_request(request_id, task, question)
        await pg_notify(self._pool, "hitl_request", {
            "request_id": str(request_id),
            "thread_id": task.thread_id,
            "agent_id": task.agent_id,
            "team_id": task.team_id,
            "prompt": question.prompt,
        })

        log.info(
            "HITL question created, waiting for answer",
            extra={
                "task_id": str(task.task_id),
                "request_id": str(request_id),
                "agent_id": task.agent_id,
            },
        )

        result = await self._waiter.wait_for(str(request_id), timeout=timeout)
        response_text = result.get("response", "")
        log.info(
            "HITL answer received",
            extra={
                "task_id": str(task.task_id),
                "request_id": str(request_id),
                "reviewer": result.get("reviewer", "unknown"),
            },
        )
        return response_text

    async def _insert_request(
        self,
        request_id: UUID,
        task: Task,
        question: QuestionEvent,
    ) -> None:
        """Insert a hitl_request row."""
        import json
        await self._pool.execute(
            """
            INSERT INTO project.hitl_requests
                (id, thread_id, agent_id, team_id, request_type, prompt, context, channel, status)
            VALUES ($1, $2, $3, $4, 'question', $5, $6, 'docker', 'pending')
            """,
            request_id,
            task.thread_id,
            task.agent_id,
            task.team_id,
            question.prompt,
            json.dumps(question.context, ensure_ascii=False, default=str),
        )
