"""Artifact persistence on disk and in database."""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Optional
from uuid import UUID

import asyncpg

from core.config import settings
from models.task import ArtifactEvent, Task

log = logging.getLogger(__name__)


class ArtifactStore:
    """Persists deliverables to the filesystem and registers them in DB."""

    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    async def persist(
        self,
        task: Task,
        artifact: ArtifactEvent,
        workflow: str = "main",
    ) -> str:
        """Write artifact to disk and insert into dispatcher_task_artifacts.

        Returns the file path where the artifact was saved.
        """
        # Resolve workflow name from project_workflows if workflow_id is set
        wf_name = workflow
        wf_id = getattr(task, "workflow_id", None)
        if wf_id is not None:
            wf_name = await self._resolve_workflow_name(wf_id) or workflow

        file_path = self._resolve_path(task, artifact, wf_name)
        self._write_file(file_path, artifact.content)

        await self._pool.execute(
            """
            INSERT INTO project.dispatcher_task_artifacts
                (task_id, key, deliverable_type, file_path, category, workflow_id)
            VALUES ($1, $2, $3, $4, $5, $6)
            """,
            task.task_id,
            artifact.key,
            artifact.deliverable_type,
            file_path,
            None,
            wf_id,
        )

        log.info(
            "Artifact persisted",
            extra={
                "task_id": str(task.task_id),
                "key": artifact.key,
                "type": artifact.deliverable_type,
                "path": file_path,
            },
        )
        return file_path

    def _resolve_path(
        self,
        task: Task,
        artifact: ArtifactEvent,
        workflow: str,
    ) -> str:
        """Build the filesystem path for an artifact."""
        slug = task.project_slug or "default"
        phase = task.phase or "unknown"
        iteration = task.iteration or 1
        phase_dir = f"{iteration}:{phase}"
        parts = [
            settings.ag_flow_root,
            "projects",
            slug,
            task.team_id,
            workflow,
            phase_dir,
            task.agent_id,
        ]
        directory = os.path.join(*parts)
        filename = artifact.key
        if not filename.endswith(".md"):
            filename += ".md"
        return os.path.join(directory, filename)

    async def _resolve_workflow_name(self, workflow_id: int) -> Optional[str]:
        """Look up workflow_name from project_workflows table."""
        row = await self._pool.fetchrow(
            "SELECT workflow_name FROM project.project_workflows WHERE id = $1",
            workflow_id,
        )
        return row["workflow_name"] if row else None

    def _write_file(self, file_path: str, content: str) -> None:
        """Write content to file, creating directories as needed."""
        path = Path(file_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
