"""Git operations service — clone, init, status via subprocess."""

from __future__ import annotations

import asyncio
import os
from typing import Optional

import structlog

from core.config import settings
from schemas.project import GitConfig, GitStatusResponse, GitTestResponse
from services.git_providers import create_repo, test_connection

log = structlog.get_logger(__name__)


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


def _full_repo_name(config: GitConfig) -> str:
    """Ensure repo_name includes owner/ prefix."""
    if "/" in config.repo_name:
        return config.repo_name
    return f"{config.login}/{config.repo_name}"


def _build_clone_url(config: GitConfig) -> str:
    """Build a clone URL with embedded credentials."""
    repo = _full_repo_name(config)
    if config.service == "github":
        return f"https://{config.login}:{config.token}@github.com/{repo}.git"
    if config.service == "gitlab":
        return f"https://oauth2:{config.token}@gitlab.com/{repo}.git"
    if config.service in ("gitea", "forgejo"):
        host = config.url.replace("https://", "").replace("http://", "").rstrip("/")
        return f"https://{config.login}:{config.token}@{host}/{repo}.git"
    if config.service == "bitbucket":
        return f"https://{config.login}:{config.token}@bitbucket.org/{repo}.git"
    # Fallback: use git_url directly
    return config.url


async def test_git_connection(config: GitConfig) -> GitTestResponse:
    """Proxy to git_providers.test_connection."""
    return await test_connection(config)


async def list_remote_branches(config: GitConfig) -> list[str]:
    """List branches on a remote repo via git ls-remote (no clone needed)."""
    clone_url = _build_clone_url(config)
    proc = await asyncio.create_subprocess_exec(
        "git", "ls-remote", "--heads", clone_url,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()
    if proc.returncode != 0:
        log.warning("git_ls_remote_failed", error=stderr.decode()[:200])
        return []
    branches = []
    for line in stdout.decode().strip().splitlines():
        # Format: <hash>\trefs/heads/<branch>
        parts = line.split("\t")
        if len(parts) == 2 and parts[1].startswith("refs/heads/"):
            branches.append(parts[1].removeprefix("refs/heads/"))
    return sorted(branches)


async def ensure_branch_structure(slug: str) -> list[str]:
    """Ensure the repo has main -> uat -> dev branch structure.

    Creates missing branches and pushes them. Returns list of created branches.
    """
    repo = _repo_path(slug)
    if not os.path.isdir(os.path.join(repo, ".git")):
        return []

    # Fetch all remote branches
    await _run_git(repo, "fetch", "--all")

    # Detect the main branch name (main or master)
    rc, out, _ = await _run_git(repo, "branch", "-r")
    remote_branches = [b.strip().removeprefix("origin/") for b in out.splitlines() if b.strip() and "HEAD" not in b]
    main_branch = "main" if "main" in remote_branches else ("master" if "master" in remote_branches else "")

    if not main_branch:
        log.warning("ensure_branches_no_main", slug=slug, branches=remote_branches)
        return []

    created: list[str] = []

    # Ensure uat exists (from main)
    if "uat" not in remote_branches:
        rc, _, err = await _run_git(repo, "checkout", "-b", "uat", f"origin/{main_branch}")
        if rc == 0:
            rc, _, err = await _run_git(repo, "push", "-u", "origin", "uat")
            if rc == 0:
                created.append("uat")
                log.info("branch_created", slug=slug, branch="uat", from_branch=main_branch)
            else:
                log.error("branch_push_failed", slug=slug, branch="uat", stderr=err[:200])
        else:
            log.error("branch_create_failed", slug=slug, branch="uat", stderr=err[:200])

    # Ensure dev exists (from uat)
    if "dev" not in remote_branches:
        # Make sure we're on uat
        source = "origin/uat" if "uat" in remote_branches or "uat" in created else f"origin/{main_branch}"
        rc, _, err = await _run_git(repo, "checkout", "-b", "dev", source)
        if rc == 0:
            rc, _, err = await _run_git(repo, "push", "-u", "origin", "dev")
            if rc == 0:
                created.append("dev")
                log.info("branch_created", slug=slug, branch="dev", from_branch=source)
            else:
                log.error("branch_push_failed", slug=slug, branch="dev", stderr=err[:200])
        else:
            log.error("branch_create_failed", slug=slug, branch="dev", stderr=err[:200])

    # Work on dev branch
    await _run_git(repo, "checkout", "dev")

    return created


async def clone_repo(slug: str, config: GitConfig) -> bool:
    """Clone a remote repository into the project repo directory."""
    repo = _repo_path(slug)
    if os.path.isdir(os.path.join(repo, ".git")):
        log.info("git_repo_already_cloned", slug=slug)
        await ensure_branch_structure(slug)
        return True

    clone_url = _build_clone_url(config)
    rc, out, err = await _run_git(
        os.path.dirname(repo), "clone", clone_url, "repo",
    )
    if rc != 0:
        log.error("git_clone_failed", slug=slug, stderr=err[:300])
        return False

    log.info("git_cloned", slug=slug)
    await ensure_branch_structure(slug)
    return True


async def init_repo(slug: str, config: GitConfig) -> bool:
    """Initialize a new git repo, add remote, make initial commit."""
    repo = _repo_path(slug)
    os.makedirs(repo, exist_ok=True)

    if not os.path.isdir(os.path.join(repo, ".git")):
        rc, _, err = await _run_git(repo, "init")
        if rc != 0:
            log.error("git_init_failed", slug=slug, stderr=err[:300])
            return False

    clone_url = _build_clone_url(config)
    await _run_git(repo, "remote", "remove", "origin")
    rc, _, err = await _run_git(repo, "remote", "add", "origin", clone_url)
    if rc != 0:
        log.error("git_remote_add_failed", slug=slug, stderr=err[:300])
        return False

    # Create .gitkeep so there is at least one file
    gitkeep = os.path.join(repo, ".gitkeep")
    if not os.path.exists(gitkeep):
        with open(gitkeep, "w") as f:
            f.write("")

    await _run_git(repo, "add", ".")
    await _run_git(repo, "commit", "-m", "Initial commit")

    rc, _, err = await _run_git(repo, "push", "-u", "origin", "main")
    if rc != 0:
        # Try master branch as fallback
        rc, _, err = await _run_git(repo, "push", "-u", "origin", "master")
        if rc != 0:
            log.warning("git_push_failed", slug=slug, stderr=err[:300])

    # Create uat and dev branches
    await ensure_branch_structure(slug)

    log.info("git_repo_initialized", slug=slug)
    return True


async def init_or_clone(slug: str, config: GitConfig) -> bool:
    """Clone existing repo or create + init a new one."""
    result = await test_connection(config)
    if result.repo_exists:
        return await clone_repo(slug, config)

    created = await create_repo(config)
    if not created:
        log.error("git_create_repo_failed", slug=slug)
        return False

    return await init_repo(slug, config)


async def get_status(slug: str) -> GitStatusResponse:
    """Get the git status of a project repo."""
    repo = _repo_path(slug)
    if not os.path.isdir(os.path.join(repo, ".git")):
        return GitStatusResponse(branch="", clean=True, ahead=0, behind=0)

    # Current branch
    rc, branch_out, _ = await _run_git(repo, "rev-parse", "--abbrev-ref", "HEAD")
    branch = branch_out.strip() if rc == 0 else "unknown"

    # Clean status
    rc, status_out, _ = await _run_git(repo, "status", "--porcelain")
    clean = len(status_out.strip()) == 0

    # Ahead/behind
    ahead = 0
    behind = 0
    tracking_ref = f"origin/{branch}"
    rc, rev_out, _ = await _run_git(
        repo, "rev-list", "--left-right", "--count",
        f"{tracking_ref}...HEAD",
    )
    if rc == 0:
        parts = rev_out.strip().split()
        if len(parts) == 2:
            behind = int(parts[0])
            ahead = int(parts[1])

    return GitStatusResponse(
        branch=branch, clean=clean, ahead=ahead, behind=behind,
    )
