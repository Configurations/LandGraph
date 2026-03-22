"""Pull request service — CRUD, merge."""

from __future__ import annotations

import asyncio
import os
from typing import Optional

import structlog

from core.config import settings
from core.database import execute, fetch_all, fetch_one
from schemas.pr import PRCreate, PRResponse, PRStatusUpdate
from services.activity_service import log_activity
from services.inbox_service import create_notification
from services.pr_remote import create_remote_pr

log = structlog.get_logger(__name__)

VALID_STATUSES = {"pending", "approved", "changes_requested", "draft", "merged"}


def _repo_path(slug: str) -> str:
    """Return the repo directory for a project."""
    return os.path.join(settings.ag_flow_root, "projects", slug, "repo")


async def _run_git(cwd: str, *args: str) -> tuple[int, str, str]:
    """Execute a git command and return (returncode, stdout, stderr)."""
    proc = await asyncio.create_subprocess_exec(
        "git", *args,
        cwd=cwd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout_bytes, stderr_bytes = await proc.communicate()
    rc = proc.returncode or 0
    return rc, stdout_bytes.decode("utf-8", errors="replace"), stderr_bytes.decode("utf-8", errors="replace")


def _row_to_response(row: dict, issue_title: Optional[str] = None) -> PRResponse:
    """Map a database row to PRResponse."""
    return PRResponse(
        id=row["id"],
        title=row["title"],
        author=row["author"],
        issue_id=row.get("issue_id"),
        issue_title=issue_title or row.get("issue_title"),
        status=row.get("status", "draft"),
        additions=row.get("additions", 0),
        deletions=row.get("deletions", 0),
        files=row.get("files", 0),
        branch=row.get("branch", ""),
        remote_url=row.get("remote_url", ""),
        project_slug=row.get("project_slug", ""),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        merged_by=row.get("merged_by"),
        merged_at=row.get("merged_at"),
    )


async def list_prs(
    project_slug: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
) -> list[PRResponse]:
    """List pull requests with optional filters."""
    query = """
        SELECT pr.*, i.title AS issue_title
        FROM project.pm_pull_requests pr
        LEFT JOIN project.pm_issues i ON pr.issue_id = i.id
        WHERE 1=1
    """
    args: list = []
    idx = 1

    if project_slug is not None:
        query += f" AND pr.project_slug = ${idx}"
        args.append(project_slug)
        idx += 1
    if status is not None:
        query += f" AND pr.status = ${idx}"
        args.append(status)
        idx += 1

    query += f" ORDER BY pr.created_at DESC LIMIT ${idx} OFFSET ${idx + 1}"
    args.extend([limit, offset])

    rows = await fetch_all(query, *args)
    return [_row_to_response(r, r.get("issue_title")) for r in rows]


async def get_pr(pr_id: str) -> Optional[PRResponse]:
    """Get a single pull request by ID."""
    row = await fetch_one(
        """
        SELECT pr.*, i.title AS issue_title
        FROM project.pm_pull_requests pr
        LEFT JOIN project.pm_issues i ON pr.issue_id = i.id
        WHERE pr.id = $1
        """,
        pr_id,
    )
    if row is None:
        return None
    return _row_to_response(row, row.get("issue_title"))


async def _get_diff_stats(repo: str, branch: str) -> tuple[int, int, int]:
    """Get additions, deletions, file count from diff against main."""
    rc, out, _ = await _run_git(repo, "diff", "--shortstat", "main..." + branch)
    if rc != 0 or not out.strip():
        return 0, 0, 0

    additions = 0
    deletions = 0
    files = 0
    parts = out.strip().split(",")
    for part in parts:
        part = part.strip()
        if "file" in part:
            files = int(part.split()[0])
        elif "insertion" in part:
            additions = int(part.split()[0])
        elif "deletion" in part:
            deletions = int(part.split()[0])
    return additions, deletions, files


async def create_pr(
    data: PRCreate,
    user_email: str,
) -> PRResponse:
    """Create a pull request — compute diff stats and try remote creation."""
    from uuid import uuid4

    pr_id = f"PR-{uuid4().hex[:8].upper()}"
    slug = data.project_slug
    additions, deletions, files = 0, 0, 0

    repo = _repo_path(slug) if slug else ""
    if repo and os.path.isdir(os.path.join(repo, ".git")):
        additions, deletions, files = await _get_diff_stats(repo, data.branch)

    remote_url = ""
    if slug:
        remote_url = await create_remote_pr(slug, data.branch, data.title)

    row = await fetch_one(
        """
        INSERT INTO project.pm_pull_requests
            (id, title, author, issue_id, status, additions, deletions,
             files, branch, remote_url, project_slug)
        VALUES ($1, $2, $3, $4, 'pending', $5, $6, $7, $8, $9, $10)
        RETURNING *
        """,
        pr_id, data.title, user_email, data.issue_id,
        additions, deletions, files,
        data.branch, remote_url, slug,
    )

    # Log activity if project exists
    proj_row = await fetch_one(
        "SELECT id FROM project.pm_projects WHERE slug = $1", slug,
    )
    if proj_row:
        await log_activity(proj_row["id"], user_email, "pr_created", pr_id, data.title)

    log.info("pr_created", pr_id=pr_id, branch=data.branch)
    return _row_to_response(row)


async def update_status(
    pr_id: str,
    data: PRStatusUpdate,
    user_email: str,
) -> Optional[PRResponse]:
    """Update the status of a pull request."""
    if data.status not in VALID_STATUSES:
        return None

    current = await fetch_one(
        "SELECT * FROM project.pm_pull_requests WHERE id = $1", pr_id,
    )
    if current is None:
        return None

    await execute(
        "UPDATE project.pm_pull_requests SET status = $1, updated_at = NOW() WHERE id = $2",
        data.status, pr_id,
    )

    slug = current.get("project_slug", "")
    proj_row = await fetch_one(
        "SELECT id FROM project.pm_projects WHERE slug = $1", slug,
    ) if slug else None

    if proj_row:
        detail = f"{data.status}"
        if data.comment:
            detail += f" - {data.comment}"
        await log_activity(proj_row["id"], user_email, "pr_status_changed", pr_id, detail)

    author = current["author"]
    if author and author != user_email:
        text = f"{user_email} changed PR {pr_id} status to {data.status}"
        await create_notification(author, "review", text, issue_id=current.get("issue_id"))

    return await get_pr(pr_id)


async def merge_pr(
    pr_id: str,
    user_email: str,
) -> Optional[PRResponse]:
    """Merge a pull request — git merge + update DB."""
    current = await fetch_one(
        "SELECT * FROM project.pm_pull_requests WHERE id = $1", pr_id,
    )
    if current is None:
        return None

    if current["status"] not in ("approved", "pending"):
        log.warning("pr_merge_not_allowed", pr_id=pr_id, status=current["status"])
        return None

    slug = current.get("project_slug", "")
    branch = current.get("branch", "")
    repo = _repo_path(slug) if slug else ""

    if repo and branch and os.path.isdir(os.path.join(repo, ".git")):
        rc, _, err = await _run_git(repo, "checkout", "main")
        if rc != 0:
            log.error("pr_merge_checkout_failed", pr_id=pr_id, stderr=err[:200])
            return None

        rc, _, err = await _run_git(repo, "merge", branch)
        if rc != 0:
            log.error("pr_merge_failed", pr_id=pr_id, stderr=err[:200])
            await _run_git(repo, "merge", "--abort")
            return None

        await _run_git(repo, "push", "origin", "main")
        await _run_git(repo, "branch", "-d", branch)

    await execute(
        """
        UPDATE project.pm_pull_requests
        SET status = 'merged', merged_by = $1, merged_at = NOW(), updated_at = NOW()
        WHERE id = $2
        """,
        user_email, pr_id,
    )

    proj_row = await fetch_one(
        "SELECT id FROM project.pm_projects WHERE slug = $1", slug,
    ) if slug else None
    if proj_row:
        await log_activity(proj_row["id"], user_email, "pr_merged", pr_id, branch)

    log.info("pr_merged", pr_id=pr_id, merged_by=user_email)
    return await get_pr(pr_id)
