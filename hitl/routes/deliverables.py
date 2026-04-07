"""Deliverable routes — list, detail, validate, remarks, branches."""

from __future__ import annotations

import os
from typing import Optional

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query

from core.config import settings
from core.security import TokenData, get_current_user
from schemas.deliverable import (
    BranchDiffResponse,
    BranchInfo,
    DeliverableDetail,
    DeliverableResponse,
    RemarkResponse,
    UpdateContentRequest,
    ValidateRequest,
    RemarkRequest,
)
from services import deliverable_service
from services.git_service import _run_git

log = structlog.get_logger(__name__)

router = APIRouter(tags=["deliverables"])


def _repo_path(slug: str) -> str:
    """Return the repo directory for a project."""
    return os.path.join(settings.ag_flow_root, "projects", slug, "repo")


@router.get("/api/projects/{slug}/deliverables", response_model=list[DeliverableResponse])
async def list_deliverables(
    slug: str,
    phase: Optional[str] = Query(None),
    agent_id: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    user: TokenData = Depends(get_current_user),
) -> list[DeliverableResponse]:
    """List deliverables for a project."""
    return await deliverable_service.list_deliverables(
        slug, phase=phase, agent_id=agent_id, status=status,
    )


@router.get("/api/deliverables/{artifact_id}", response_model=DeliverableDetail)
async def get_deliverable(
    artifact_id: int,
    user: TokenData = Depends(get_current_user),
) -> DeliverableDetail:
    """Get deliverable detail with content."""
    result = await deliverable_service.get_deliverable(artifact_id)
    if result is None:
        raise HTTPException(status_code=404, detail="deliverable.not_found")
    return result


@router.put("/api/deliverables/{artifact_id}/content")
async def update_content(
    artifact_id: int,
    body: UpdateContentRequest,
    user: TokenData = Depends(get_current_user),
) -> dict:
    """Update deliverable markdown content on disk."""
    ok = await deliverable_service.update_content(artifact_id, body.content)
    if not ok:
        raise HTTPException(status_code=404, detail="deliverable.write_failed")
    return {"ok": True}


@router.post("/api/deliverables/{artifact_id}/validate")
async def validate_deliverable(
    artifact_id: int,
    body: ValidateRequest,
    user: TokenData = Depends(get_current_user),
) -> dict:
    """Approve or reject a deliverable."""
    if body.verdict not in ("approved", "rejected"):
        raise HTTPException(status_code=400, detail="deliverable.invalid_verdict")
    ok = await deliverable_service.validate_deliverable(
        artifact_id, body.verdict, user.email, body.comment,
    )
    if not ok:
        raise HTTPException(status_code=404, detail="deliverable.not_found")
    return {"ok": True, "verdict": body.verdict}


@router.post("/api/deliverables/{artifact_id}/remark", response_model=RemarkResponse)
async def submit_remark(
    artifact_id: int,
    body: RemarkRequest,
    user: TokenData = Depends(get_current_user),
) -> RemarkResponse:
    """Add a remark to a deliverable."""
    return await deliverable_service.submit_remark(artifact_id, user.email, body.comment)


@router.get("/api/deliverables/{artifact_id}/remarks", response_model=list[RemarkResponse])
async def list_remarks(
    artifact_id: int,
    user: TokenData = Depends(get_current_user),
) -> list[RemarkResponse]:
    """List all remarks for a deliverable."""
    return await deliverable_service.list_remarks(artifact_id)


@router.post("/api/deliverables/{artifact_id}/revise")
async def revise_deliverable_route(
    artifact_id: int,
    body: RemarkRequest,
    user: TokenData = Depends(get_current_user),
) -> dict:
    """Send a revision comment and re-dispatch the agent for correction."""
    try:
        return await deliverable_service.revise_deliverable(artifact_id, body.comment, user.email)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/api/projects/{slug}/branches", response_model=list[BranchInfo])
async def list_branches(
    slug: str,
    user: TokenData = Depends(get_current_user),
) -> list[BranchInfo]:
    """List temp/* branches in the project repo."""
    repo = _repo_path(slug)
    if not os.path.isdir(os.path.join(repo, ".git")):
        return []

    rc, out, _ = await _run_git(repo, "branch", "-a", "--format=%(refname:short)")
    if rc != 0:
        return []

    branches: list[BranchInfo] = []
    for line in out.strip().splitlines():
        name = line.strip()
        if not name or not name.startswith("temp/"):
            continue
        # Get last commit message
        rc2, commit_out, _ = await _run_git(repo, "log", "-1", "--format=%s", name)
        last_commit = commit_out.strip() if rc2 == 0 else ""
        branches.append(BranchInfo(name=name, last_commit=last_commit))

    return branches


@router.get("/api/projects/{slug}/branches/{branch:path}/diff", response_model=BranchDiffResponse)
async def branch_diff(
    slug: str,
    branch: str,
    user: TokenData = Depends(get_current_user),
) -> BranchDiffResponse:
    """Get diff between a branch and dev."""
    repo = _repo_path(slug)
    if not os.path.isdir(os.path.join(repo, ".git")):
        raise HTTPException(status_code=404, detail="git.no_repo")

    diff_ref = f"dev..{branch}"

    # Stat diff
    rc, stat_out, _ = await _run_git(repo, "diff", diff_ref, "--stat", "--numstat")
    files: list[dict] = []
    if rc == 0:
        for line in stat_out.strip().splitlines():
            parts = line.split("\t")
            if len(parts) >= 3:
                additions = int(parts[0]) if parts[0] != "-" else 0
                deletions = int(parts[1]) if parts[1] != "-" else 0
                path = parts[2]
                status = "modified"
                if additions > 0 and deletions == 0:
                    status = "added"
                elif additions == 0 and deletions > 0:
                    status = "deleted"
                files.append({
                    "path": path,
                    "status": status,
                    "additions": additions,
                    "deletions": deletions,
                })

    return BranchDiffResponse(branch=branch, files=files)
