"""Tests for services/git_service.py + git_providers.py."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from schemas.project import GitConfig, GitTestResponse


# ── Helpers ──────────────────────────────────────────────────

def _github_config(**overrides) -> GitConfig:
    defaults = dict(
        service="github", url="https://github.com",
        login="user", token="ghp_fake", repo_name="user/repo",
    )
    defaults.update(overrides)
    return GitConfig(**defaults)


def _mock_response(status_code: int, json_data=None):
    """Build a fake httpx.Response."""
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = status_code
    resp.json.return_value = json_data or {}
    resp.text = ""
    return resp


# ── test_connection (git_providers) ──────────────────────────

@pytest.mark.asyncio
async def test_connection_github_success():
    """GitHub test_connection returns connected + repo_exists on 200."""
    from services.git_providers import test_connection

    mock_resp = _mock_response(200)
    mock_client = AsyncMock()
    mock_client.get.return_value = mock_resp
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock()

    with patch("services.git_providers.httpx.AsyncClient", return_value=mock_client):
        result = await test_connection(_github_config())

    assert result.connected is True
    assert result.repo_exists is True


@pytest.mark.asyncio
async def test_connection_github_invalid_token():
    """GitHub test_connection returns auth_failed on 401."""
    from services.git_providers import test_connection

    mock_resp = _mock_response(401)
    mock_client = AsyncMock()
    mock_client.get.return_value = mock_resp
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock()

    with patch("services.git_providers.httpx.AsyncClient", return_value=mock_client):
        result = await test_connection(_github_config())

    assert result.connected is False
    assert "auth_failed" in result.message


@pytest.mark.asyncio
async def test_connection_unsupported_service():
    """Unknown service returns connected=False."""
    from services.git_providers import test_connection

    config = GitConfig(service="unknown", url="", login="", token="", repo_name="")
    result = await test_connection(config)

    assert result.connected is False
    assert "unknown_service" in result.message


# ── clone_repo ───────────────────────────────────────────────

@pytest.mark.asyncio
async def test_clone_repo_success():
    """clone_repo succeeds when git returns rc=0."""
    from services.git_service import clone_repo

    fake_proc = AsyncMock()
    fake_proc.communicate.return_value = (b"Cloning...\n", b"")
    fake_proc.returncode = 0

    with (
        patch("services.git_service.os.path.isdir", return_value=False),
        patch("services.git_service.asyncio.create_subprocess_exec", return_value=fake_proc),
    ):
        result = await clone_repo("proj", _github_config())

    assert result is True


@pytest.mark.asyncio
async def test_clone_repo_git_error():
    """clone_repo returns False when git fails (rc=1)."""
    from services.git_service import clone_repo

    fake_proc = AsyncMock()
    fake_proc.communicate.return_value = (b"", b"fatal: error\n")
    fake_proc.returncode = 1

    with (
        patch("services.git_service.os.path.isdir", return_value=False),
        patch("services.git_service.asyncio.create_subprocess_exec", return_value=fake_proc),
    ):
        result = await clone_repo("proj", _github_config())

    assert result is False


# ── init_repo ────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_init_repo_creates_dir_and_runs_git():
    """init_repo calls makedirs, git init, remote add, push."""
    from services.git_service import init_repo

    fake_proc = AsyncMock()
    fake_proc.communicate.return_value = (b"ok\n", b"")
    fake_proc.returncode = 0

    with (
        patch("services.git_service.os.makedirs") as mk,
        patch("services.git_service.os.path.isdir", return_value=False),
        patch("services.git_service.os.path.exists", return_value=False),
        patch("builtins.open", MagicMock()),
        patch("services.git_service.asyncio.create_subprocess_exec", return_value=fake_proc),
    ):
        result = await init_repo("proj", _github_config())

    assert result is True
    mk.assert_called_once()


# ── get_status ───────────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_status_parses_output():
    """get_status parses branch, clean, ahead/behind from git output."""
    from services.git_service import get_status

    call_count = 0
    outputs = [
        (0, b"main\n", b""),          # rev-parse
        (0, b"", b""),                 # status --porcelain (clean)
        (0, b"2\t3\n", b""),          # rev-list
    ]

    async def fake_exec(*args, **kwargs):
        nonlocal call_count
        proc = AsyncMock()
        out = outputs[min(call_count, len(outputs) - 1)]
        proc.communicate.return_value = (out[1], out[2])
        proc.returncode = out[0]
        call_count += 1
        return proc

    with (
        patch("services.git_service.os.path.isdir", return_value=True),
        patch("services.git_service.asyncio.create_subprocess_exec", side_effect=fake_exec),
    ):
        result = await get_status("proj")

    assert result.branch == "main"
    assert result.clean is True
    assert result.behind == 2
    assert result.ahead == 3
