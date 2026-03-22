"""Tests for services.docker_manager — container lifecycle and helpers."""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from services.docker_manager import DockerManager, _parse_mem_limit


# ── _parse_mem_limit ─────────────────────────────────


class TestParseMemLimit:
    def test_gigabytes(self):
        assert _parse_mem_limit("2g") == 2 * 1024**3

    def test_megabytes(self):
        assert _parse_mem_limit("512m") == 512 * 1024**2

    def test_kilobytes(self):
        assert _parse_mem_limit("1024k") == 1024 * 1024

    def test_bytes_suffix(self):
        assert _parse_mem_limit("4096b") == 4096

    def test_plain_number(self):
        assert _parse_mem_limit("1048576") == 1048576

    def test_uppercase_ignored(self):
        # lower() is called internally
        assert _parse_mem_limit("2G") == 2 * 1024**3

    def test_whitespace_stripped(self):
        assert _parse_mem_limit("  1g  ") == 1024**3


# ── DockerManager ────────────────────────────────────


class TestDockerManager:

    @pytest.fixture
    def manager(self):
        return DockerManager()

    @pytest.mark.asyncio
    async def test_get_client_creates_once(self, manager):
        with patch("services.docker_manager.aiodocker.Docker") as MockDocker:
            mock_instance = MagicMock()
            MockDocker.return_value = mock_instance

            client1 = await manager._get_client()
            client2 = await manager._get_client()
            assert client1 is client2
            MockDocker.assert_called_once()

    @pytest.mark.asyncio
    async def test_close_resets_client(self, manager):
        mock_client = AsyncMock()
        manager._docker = mock_client

        await manager.close()
        mock_client.close.assert_called_once()
        assert manager._docker is None

    @pytest.mark.asyncio
    async def test_close_when_no_client_is_noop(self, manager):
        await manager.close()  # should not raise

    @pytest.mark.asyncio
    async def test_create_container_returns_id(self, manager):
        mock_container = MagicMock()
        mock_container.id = "container-xyz-123"

        mock_client = AsyncMock()
        mock_client.containers.create_or_replace = AsyncMock(return_value=mock_container)
        manager._docker = mock_client

        cid = await manager.create_container(
            image="test:latest",
            env={"FOO": "bar"},
            volumes=["/host:/container"],
            mem_limit="1g",
            cpu_quota=50000,
            name="test-agent",
        )
        assert cid == "container-xyz-123"
        mock_client.containers.create_or_replace.assert_called_once()

        # Verify config passed
        call_kwargs = mock_client.containers.create_or_replace.call_args
        config = call_kwargs.kwargs.get("config") or call_kwargs[1].get("config")
        assert config["Image"] == "test:latest"
        assert config["HostConfig"]["Memory"] == 1024**3
        assert config["HostConfig"]["CpuQuota"] == 50000

    @pytest.mark.asyncio
    async def test_create_container_no_limits(self, manager):
        mock_container = MagicMock()
        mock_container.id = "cid"

        mock_client = AsyncMock()
        mock_client.containers.create_or_replace = AsyncMock(return_value=mock_container)
        manager._docker = mock_client

        await manager.create_container(
            image="img:1", env={}, volumes=[]
        )

        call_kwargs = mock_client.containers.create_or_replace.call_args
        config = call_kwargs.kwargs.get("config") or call_kwargs[1].get("config")
        assert "Memory" not in config["HostConfig"]
        assert "CpuQuota" not in config["HostConfig"]

    @pytest.mark.asyncio
    async def test_stop_container_already_stopped(self, manager):
        """304 (already stopped) should not raise."""
        import aiodocker.exceptions

        mock_container = AsyncMock()
        mock_container.stop = AsyncMock(
            side_effect=aiodocker.exceptions.DockerError(status=304, data={"message": "already stopped"})
        )

        mock_client = AsyncMock()
        mock_client.containers.get = AsyncMock(return_value=mock_container)
        manager._docker = mock_client

        # Should not raise
        await manager.stop_container("some-id")

    @pytest.mark.asyncio
    async def test_stop_container_not_found(self, manager):
        """404 should not raise."""
        import aiodocker.exceptions

        mock_client = AsyncMock()
        mock_client.containers.get = AsyncMock(
            side_effect=aiodocker.exceptions.DockerError(status=404, data={"message": "not found"})
        )
        manager._docker = mock_client

        await manager.stop_container("gone-id")

    @pytest.mark.asyncio
    async def test_stop_container_other_error_raises(self, manager):
        """Non-304/404 errors should propagate."""
        import aiodocker.exceptions

        mock_container = AsyncMock()
        mock_container.stop = AsyncMock(
            side_effect=aiodocker.exceptions.DockerError(status=500, data={"message": "server error"})
        )

        mock_client = AsyncMock()
        mock_client.containers.get = AsyncMock(return_value=mock_container)
        manager._docker = mock_client

        with pytest.raises(aiodocker.exceptions.DockerError):
            await manager.stop_container("err-id")

    @pytest.mark.asyncio
    async def test_remove_container_not_found(self, manager):
        """404 on removal should not raise."""
        import aiodocker.exceptions

        mock_client = AsyncMock()
        mock_client.containers.get = AsyncMock(
            side_effect=aiodocker.exceptions.DockerError(status=404, data={"message": "not found"})
        )
        manager._docker = mock_client

        await manager.remove_container("gone-id")

    @pytest.mark.asyncio
    async def test_remove_container_other_error_raises(self, manager):
        import aiodocker.exceptions

        mock_container = AsyncMock()
        mock_container.delete = AsyncMock(
            side_effect=aiodocker.exceptions.DockerError(status=500, data={"message": "boom"})
        )

        mock_client = AsyncMock()
        mock_client.containers.get = AsyncMock(return_value=mock_container)
        manager._docker = mock_client

        with pytest.raises(aiodocker.exceptions.DockerError):
            await manager.remove_container("err-id")

    @pytest.mark.asyncio
    async def test_wait_container_returns_exit_code(self, manager):
        mock_container = AsyncMock()
        mock_container.wait = AsyncMock(return_value={"StatusCode": 0})

        mock_client = AsyncMock()
        mock_client.containers.get = AsyncMock(return_value=mock_container)
        manager._docker = mock_client

        code = await manager.wait_container("cid")
        assert code == 0

    @pytest.mark.asyncio
    async def test_wait_container_missing_status_code(self, manager):
        mock_container = AsyncMock()
        mock_container.wait = AsyncMock(return_value={})

        mock_client = AsyncMock()
        mock_client.containers.get = AsyncMock(return_value=mock_container)
        manager._docker = mock_client

        code = await manager.wait_container("cid")
        assert code == -1

    @pytest.mark.asyncio
    async def test_get_logs_returns_string(self, manager):
        mock_container = AsyncMock()
        mock_container.log = AsyncMock(return_value=["line1\n", "line2\n"])

        mock_client = AsyncMock()
        mock_client.containers.get = AsyncMock(return_value=mock_container)
        manager._docker = mock_client

        logs = await manager.get_logs("cid", tail=100)
        assert logs == "line1\nline2\n"

    @pytest.mark.asyncio
    async def test_get_logs_docker_error_returns_empty(self, manager):
        import aiodocker.exceptions

        mock_client = AsyncMock()
        mock_client.containers.get = AsyncMock(
            side_effect=aiodocker.exceptions.DockerError(status=404, data={"message": "not found"})
        )
        manager._docker = mock_client

        logs = await manager.get_logs("gone")
        assert logs == ""


# ── managed_container context manager ────────────────


class TestManagedContainer:

    @pytest.mark.asyncio
    async def test_cleanup_on_normal_exit(self):
        manager = DockerManager()
        manager.create_container = AsyncMock(return_value="cid-ok")
        manager.stop_container = AsyncMock()
        manager.remove_container = AsyncMock()

        async with manager.managed_container(
            image="img", env={}, volumes=[]
        ) as cid:
            assert cid == "cid-ok"

        manager.stop_container.assert_called_once_with("cid-ok", timeout=5)
        manager.remove_container.assert_called_once_with("cid-ok")

    @pytest.mark.asyncio
    async def test_cleanup_on_exception(self):
        manager = DockerManager()
        manager.create_container = AsyncMock(return_value="cid-err")
        manager.stop_container = AsyncMock()
        manager.remove_container = AsyncMock()

        with pytest.raises(ValueError, match="boom"):
            async with manager.managed_container(
                image="img", env={}, volumes=[]
            ) as cid:
                raise ValueError("boom")

        manager.stop_container.assert_called_once()
        manager.remove_container.assert_called_once()

    @pytest.mark.asyncio
    async def test_cleanup_tolerates_stop_failure(self):
        manager = DockerManager()
        manager.create_container = AsyncMock(return_value="cid-x")
        manager.stop_container = AsyncMock(side_effect=RuntimeError("stop failed"))
        manager.remove_container = AsyncMock()

        async with manager.managed_container(image="img", env={}, volumes=[]) as cid:
            pass

        # remove should still be called even if stop failed
        manager.remove_container.assert_called_once_with("cid-x")

    @pytest.mark.asyncio
    async def test_cleanup_tolerates_remove_failure(self):
        manager = DockerManager()
        manager.create_container = AsyncMock(return_value="cid-y")
        manager.stop_container = AsyncMock()
        manager.remove_container = AsyncMock(side_effect=RuntimeError("rm failed"))

        # Should not raise
        async with manager.managed_container(image="img", env={}, volumes=[]) as cid:
            pass
