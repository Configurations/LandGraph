"""Remote pull request creation via git provider APIs."""

from __future__ import annotations

import os
from typing import Optional

import httpx
import structlog

from core.database import fetch_one
from services.git_providers import _auth_headers, _get_api_base, _split_owner_repo

log = structlog.get_logger(__name__)


async def create_remote_pr(
    slug: str,
    branch: str,
    title: str,
) -> str:
    """Create a remote pull request. Returns the remote URL or empty string."""
    proj = await fetch_one(
        "SELECT git_service, git_url, git_login, git_token_env, git_repo_name "
        "FROM project.pm_projects WHERE slug = $1",
        slug,
    )
    if not proj or not proj["git_service"] or proj["git_service"] == "other":
        return ""

    from schemas.project import GitConfig

    token = os.getenv(proj["git_token_env"], "")
    config = GitConfig(
        service=proj["git_service"],
        url=proj.get("git_url", ""),
        login=proj.get("git_login", ""),
        token=token,
        repo_name=proj.get("git_repo_name", ""),
    )

    base = _get_api_base(config.service, config.url)
    headers = _auth_headers(config)
    owner, repo = _split_owner_repo(config)

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            if config.service == "github":
                resp = await client.post(
                    f"{base}/repos/{owner}/{repo}/pulls",
                    headers=headers,
                    json={"title": title, "head": branch, "base": "main"},
                )
                if resp.status_code in (200, 201):
                    return resp.json().get("html_url", "")
            elif config.service == "gitlab":
                encoded = f"{owner}%2F{repo}"
                resp = await client.post(
                    f"{base}/projects/{encoded}/merge_requests",
                    headers=headers,
                    json={"title": title, "source_branch": branch, "target_branch": "main"},
                )
                if resp.status_code in (200, 201):
                    return resp.json().get("web_url", "")
    except httpx.HTTPError as exc:
        log.warning("remote_pr_creation_failed", slug=slug, error=str(exc))

    return ""
