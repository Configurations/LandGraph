"""Project CRUD service — asyncpg + disk operations."""

from __future__ import annotations

import os
import shutil
from datetime import datetime, timezone
from typing import Optional
from uuid import uuid4

import structlog

from core.config import settings
from core.database import execute, fetch_all, fetch_one
from schemas.project import ProjectCreate, ProjectResponse, SlugCheckResponse

log = structlog.get_logger(__name__)


def _projects_dir() -> str:
    """Return the base projects directory."""
    return os.path.join(settings.ag_flow_root, "projects")


def _project_dir(slug: str) -> str:
    """Return the directory for a specific project."""
    return os.path.join(_projects_dir(), slug)


def _row_to_response(row: dict) -> ProjectResponse:
    """Convert a DB row to ProjectResponse."""
    git_url = row.get("git_url", "")
    git_repo_name = row.get("git_repo_name", "")
    slug = row.get("slug", "")
    wizard_path = os.path.join(_projects_dir(), slug, "create-project.json") if slug else ""
    return ProjectResponse(
        id=str(row["id"]),
        name=row["name"],
        slug=slug,
        team_id=row["team_id"],
        language=row.get("language", "fr"),
        git_service=row.get("git_service", "other"),
        git_url=git_url,
        git_login=row.get("git_login", ""),
        git_repo_name=git_repo_name,
        git_connected=bool(git_url),
        git_repo_exists=bool(git_repo_name),
        wizard_pending=bool(wizard_path and os.path.isfile(wizard_path)),
        status=row.get("status", "on-track"),
        color=row.get("color", "#6366f1"),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


async def create_project(data: ProjectCreate) -> ProjectResponse:
    """Create a project on disk and in the database."""
    base = _project_dir(data.slug)
    for sub in ("repo", "docs", "uploads"):
        os.makedirs(os.path.join(base, sub), exist_ok=True)

    # Write .project metadata file
    now_str = datetime.now(timezone.utc).isoformat()
    project_file = os.path.join(base, ".project")
    lines = [
        f"uuid={uuid4()}",
        f"slug={data.slug}",
        f"name={data.name}",
        f"team_id={data.team_id}",
        f"language={data.language}",
        f"git_service={data.git_service}",
        f"git_url={data.git_url}",
        f"git_login={data.git_login}",
        f"created_at={now_str}",
    ]
    with open(project_file, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    row = await fetch_one(
        """INSERT INTO project.pm_projects
           (name, slug, team_id, language, git_service, git_url,
            git_login, git_token_env, git_repo_name, lead, description)
           VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
           RETURNING *""",
        data.name, data.slug, data.team_id, data.language,
        data.git_service, data.git_url, data.git_login,
        data.git_token, data.git_repo_name,
        data.team_id, data.name,
    )
    if not row:
        raise RuntimeError("project.insert_failed")

    log.info("project_created", slug=data.slug, team_id=data.team_id)
    return _row_to_response(row)


async def check_slug_exists(slug: str) -> SlugCheckResponse:
    """Check if a project slug already exists in the database."""
    path = _project_dir(slug)
    row = await fetch_one(
        "SELECT 1 FROM project.pm_projects WHERE slug = $1", slug,
    )
    return SlugCheckResponse(exists=row is not None, path=path)


async def get_project(slug: str) -> Optional[ProjectResponse]:
    """Fetch a single project by slug."""
    row = await fetch_one(
        "SELECT * FROM project.pm_projects WHERE slug = $1", slug,
    )
    if not row:
        return None
    return _row_to_response(row)


async def list_projects(
    team_id: Optional[str],
    user_teams: list[str],
    role: str,
) -> list[ProjectResponse]:
    """List projects filtered by access rights."""
    if role == "admin":
        if team_id:
            rows = await fetch_all(
                "SELECT * FROM project.pm_projects WHERE team_id = $1 ORDER BY created_at DESC",
                team_id,
            )
        else:
            rows = await fetch_all(
                "SELECT * FROM project.pm_projects ORDER BY created_at DESC",
            )
    else:
        if team_id:
            if team_id not in user_teams:
                return []
            rows = await fetch_all(
                "SELECT * FROM project.pm_projects WHERE team_id = $1 ORDER BY created_at DESC",
                team_id,
            )
        else:
            if not user_teams:
                return []
            rows = await fetch_all(
                "SELECT * FROM project.pm_projects WHERE team_id = ANY($1) ORDER BY created_at DESC",
                user_teams,
            )
    return [_row_to_response(r) for r in rows]


async def delete_project(slug: str) -> bool:
    """Delete a project from the database and remove its directory from disk."""
    result = await execute(
        "DELETE FROM project.pm_projects WHERE slug = $1", slug,
    )
    # Remove disk directory
    path = _project_dir(slug)
    if os.path.isdir(path):
        shutil.rmtree(path, ignore_errors=True)

    log.info("project_deleted", slug=slug)
    return True
