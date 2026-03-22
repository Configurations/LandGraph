"""Git provider API definitions and HTTP helpers."""

from __future__ import annotations

from typing import Any, Optional

import httpx
import structlog

from schemas.project import GitConfig, GitTestResponse

log = structlog.get_logger(__name__)

# Provider API templates — {url} is replaced by git_url for self-hosted
GIT_PROVIDERS: dict[str, dict[str, str]] = {
    "github": {
        "api": "https://api.github.com",
        "check": "/repos/{owner}/{repo}",
        "create": "/user/repos",
    },
    "gitlab": {
        "api": "https://gitlab.com/api/v4",
        "check": "/projects/{owner}%2F{repo}",
        "create": "/projects",
    },
    "gitea": {
        "api": "{url}/api/v1",
        "check": "/repos/{owner}/{repo}",
        "create": "/user/repos",
    },
    "forgejo": {
        "api": "{url}/api/v1",
        "check": "/repos/{owner}/{repo}",
        "create": "/user/repos",
    },
    "bitbucket": {
        "api": "https://api.bitbucket.org/2.0",
        "check": "/repositories/{owner}/{repo}",
        "create": "/repositories/{owner}/{repo}",
    },
}


def _get_api_base(service: str, url: str) -> str:
    """Resolve the API base URL for a provider."""
    provider = GIT_PROVIDERS.get(service)
    if not provider:
        return ""
    base = provider["api"]
    if "{url}" in base:
        clean_url = url.rstrip("/")
        base = base.replace("{url}", clean_url)
    return base


def _auth_headers(config: GitConfig) -> dict[str, str]:
    """Build authentication headers for the provider."""
    token = config.token
    if not token:
        return {}
    if config.service in ("github", "gitea", "forgejo"):
        return {"Authorization": f"token {token}"}
    if config.service == "gitlab":
        return {"PRIVATE-TOKEN": token}
    if config.service == "bitbucket":
        return {"Authorization": f"Bearer {token}"}
    return {"Authorization": f"Bearer {token}"}


def _split_owner_repo(config: GitConfig) -> tuple[str, str]:
    """Extract owner and repo from config."""
    repo_name = config.repo_name
    if "/" in repo_name:
        parts = repo_name.split("/", 1)
        return parts[0], parts[1]
    return config.login, repo_name


async def test_connection(config: GitConfig) -> GitTestResponse:
    """Test connection to a git provider and check repo existence."""
    provider = GIT_PROVIDERS.get(config.service)
    if not provider:
        return GitTestResponse(
            connected=False, repo_exists=False,
            message="git.unknown_service",
        )

    base = _get_api_base(config.service, config.url)
    headers = _auth_headers(config)
    owner, repo = _split_owner_repo(config)
    check_path = provider["check"].format(owner=owner, repo=repo)

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(f"{base}{check_path}", headers=headers)
    except httpx.HTTPError as exc:
        msg = str(exc)
        return GitTestResponse(
            connected=False, repo_exists=False,
            message=f"git.connection_error: {msg}",
        )

    if resp.status_code == 200:
        return GitTestResponse(connected=True, repo_exists=True)
    if resp.status_code == 404:
        return GitTestResponse(
            connected=True, repo_exists=False,
            message="git.repo_not_found",
        )
    if resp.status_code in (401, 403):
        return GitTestResponse(
            connected=False, repo_exists=False,
            message="git.auth_failed",
        )
    return GitTestResponse(
        connected=True, repo_exists=False,
        message=f"git.unexpected_status:{resp.status_code}",
    )


async def create_repo(config: GitConfig) -> bool:
    """Create a remote repository via the provider API."""
    provider = GIT_PROVIDERS.get(config.service)
    if not provider or "create" not in provider:
        return False

    base = _get_api_base(config.service, config.url)
    headers = _auth_headers(config)
    owner, repo = _split_owner_repo(config)

    body: dict[str, Any] = {"name": repo}
    if config.service == "gitlab":
        body = {"name": repo, "path": repo}
    elif config.service == "bitbucket":
        body = {"scm": "git", "is_private": True}

    create_path = provider["create"].format(owner=owner, repo=repo)
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"{base}{create_path}", headers=headers, json=body,
            )
    except httpx.HTTPError:
        log.error("git_create_repo_failed", service=config.service)
        return False

    success = resp.status_code in (200, 201)
    if not success:
        log.warning(
            "git_create_repo_error",
            status=resp.status_code, body=resp.text[:200],
        )
    return success
