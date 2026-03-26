"""Project routes — CRUD, git operations."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException

from core.security import TokenData, get_current_user
from schemas.project import (
    GitConfig,
    GitStatusResponse,
    GitTestResponse,
    ProjectCreate,
    ProjectResponse,
    SlugCheckResponse,
)
from schemas.wizard import WizardStepBody
from services import git_service, project_service, wizard_data_service

router = APIRouter(prefix="/api/projects", tags=["projects"])


def _check_team_access(user: TokenData, team_id: str) -> None:
    """Raise 403 if user has no access to the team."""
    if user.role == "admin":
        return
    if team_id not in user.teams:
        raise HTTPException(status_code=403, detail="team.access_denied")


@router.post("", response_model=ProjectResponse)
async def create_project(
    data: ProjectCreate,
    user: TokenData = Depends(get_current_user),
) -> ProjectResponse:
    """Create a new project."""
    _check_team_access(user, data.team_id)
    existing = await project_service.check_slug_exists(data.slug)
    if existing.exists:
        raise HTTPException(status_code=409, detail="project.slug_exists")
    return await project_service.create_project(data)


@router.get("", response_model=list[ProjectResponse])
async def list_projects(
    team_id: Optional[str] = None,
    user: TokenData = Depends(get_current_user),
) -> list[ProjectResponse]:
    """List projects visible to the current user."""
    return await project_service.list_projects(
        team_id=team_id,
        user_teams=user.teams,
        role=user.role,
    )


# ── Static paths BEFORE /{slug} to avoid route conflicts ────

@router.get("/check-slug", response_model=SlugCheckResponse)
async def check_slug(
    slug: str,
    user: TokenData = Depends(get_current_user),
) -> SlugCheckResponse:
    """Check if a project slug already exists."""
    return await project_service.check_slug_exists(slug)


@router.post("/git/test", response_model=GitTestResponse)
async def test_git_standalone(
    config: GitConfig,
    user: TokenData = Depends(get_current_user),
) -> GitTestResponse:
    """Test git connection (no project required — used during wizard)."""
    return await git_service.test_git_connection(config)


@router.post("/git/branches")
async def list_remote_branches(
    config: GitConfig,
    user: TokenData = Depends(get_current_user),
) -> dict:
    """List branches on a remote repo (no project required — used during wizard)."""
    branches = await git_service.list_remote_branches(config)
    return {"branches": branches}


# ── Dynamic /{slug} paths ───────────────────────────────────

@router.get("/{slug}", response_model=ProjectResponse)
async def get_project(
    slug: str,
    user: TokenData = Depends(get_current_user),
) -> ProjectResponse:
    """Get a single project by slug."""
    project = await project_service.get_project(slug)
    if not project:
        raise HTTPException(status_code=404, detail="project.not_found")
    _check_team_access(user, project.team_id)
    return project


@router.delete("/{slug}")
async def delete_project(
    slug: str,
    user: TokenData = Depends(get_current_user),
) -> dict:
    """Delete a project. Removes DB record and disk directory."""
    project = await project_service.get_project(slug)
    if not project:
        raise HTTPException(status_code=404, detail="project.not_found")
    await project_service.delete_project(slug)
    return {"ok": True}


@router.post("/{slug}/git/test", response_model=GitTestResponse)
async def test_git(
    slug: str,
    config: GitConfig,
    user: TokenData = Depends(get_current_user),
) -> GitTestResponse:
    """Test git connection for an existing project."""
    project = await project_service.get_project(slug)
    if not project:
        raise HTTPException(status_code=404, detail="project.not_found")
    _check_team_access(user, project.team_id)
    return await git_service.test_git_connection(config)


@router.post("/{slug}/git/init", response_model=dict)
async def init_git(
    slug: str,
    config: GitConfig,
    user: TokenData = Depends(get_current_user),
) -> dict:
    """Initialize or clone a git repo for a project."""
    project = await project_service.get_project(slug)
    if not project:
        raise HTTPException(status_code=404, detail="project.not_found")
    _check_team_access(user, project.team_id)
    success = await git_service.init_or_clone(slug, config)
    if not success:
        raise HTTPException(status_code=500, detail="git.init_failed")
    return {"ok": True}


@router.get("/{slug}/git/status", response_model=GitStatusResponse)
async def git_status(
    slug: str,
    user: TokenData = Depends(get_current_user),
) -> GitStatusResponse:
    """Get git status for a project repo."""
    project = await project_service.get_project(slug)
    if not project:
        raise HTTPException(status_code=404, detail="project.not_found")
    _check_team_access(user, project.team_id)
    return await git_service.get_status(slug)


# ── Wizard data ─────────────────────────────────────────────────


@router.get("/{slug}/wizard-data")
async def get_wizard_data(
    slug: str,
    user: TokenData = Depends(get_current_user),
) -> list[dict]:
    """Read all wizard step data for a project."""
    return await wizard_data_service.get_wizard_data(slug)


@router.put("/{slug}/wizard-data/{step_id}")
async def save_wizard_step(
    slug: str,
    step_id: int,
    body: WizardStepBody,
    user: TokenData = Depends(get_current_user),
) -> list[dict]:
    """Save a wizard step's data. No DB check — directory is created on the fly."""
    return await wizard_data_service.save_step(slug, step_id, body.data)


@router.delete("/{slug}/wizard-data")
async def delete_wizard_data(
    slug: str,
    user: TokenData = Depends(get_current_user),
) -> dict:
    """Delete create-project.json — marks wizard as complete."""
    await wizard_data_service.delete_wizard_data(slug)
    return {"ok": True}
