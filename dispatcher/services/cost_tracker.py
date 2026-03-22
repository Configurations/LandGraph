"""Cost tracking and aggregation per agent/phase/project."""

from __future__ import annotations

import logging
from typing import Optional
from uuid import UUID

import asyncpg

log = logging.getLogger(__name__)


class CostTracker:
    """Records and aggregates costs for agent task executions."""

    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    async def record(
        self,
        task_id: UUID,
        project_slug: Optional[str],
        team_id: str,
        phase: str,
        agent_id: str,
        cost_usd: float,
    ) -> None:
        """Record cost on the task and update the summary table."""
        await self._pool.execute(
            "UPDATE project.dispatcher_tasks SET cost_usd = $1 WHERE id = $2",
            cost_usd,
            task_id,
        )

        if not project_slug:
            return

        await self._pool.execute(
            """
            INSERT INTO project.dispatcher_cost_summary
                (project_slug, team_id, phase, agent_id, total_cost_usd, task_count, avg_cost_per_task, last_updated)
            VALUES ($1, $2, $3, $4, $5, 1, $5, NOW())
            ON CONFLICT (project_slug, team_id, phase, agent_id)
            DO UPDATE SET
                total_cost_usd = project.dispatcher_cost_summary.total_cost_usd + EXCLUDED.total_cost_usd,
                task_count = project.dispatcher_cost_summary.task_count + 1,
                avg_cost_per_task = (project.dispatcher_cost_summary.total_cost_usd + EXCLUDED.total_cost_usd)
                                   / (project.dispatcher_cost_summary.task_count + 1),
                last_updated = NOW()
            """,
            project_slug,
            team_id,
            phase,
            agent_id,
            cost_usd,
        )
        log.info(
            "Cost recorded",
            extra={
                "task_id": str(task_id),
                "agent_id": agent_id,
                "cost_usd": cost_usd,
            },
        )

    async def get_project_costs(self, project_slug: str) -> list[dict]:
        """Get cost summary for a project, grouped by phase and agent."""
        rows = await self._pool.fetch(
            """
            SELECT project_slug, team_id, phase, agent_id,
                   total_cost_usd, task_count, avg_cost_per_task
            FROM project.dispatcher_cost_summary
            WHERE project_slug = $1
            ORDER BY phase, agent_id
            """,
            project_slug,
        )
        return [dict(r) for r in rows]
