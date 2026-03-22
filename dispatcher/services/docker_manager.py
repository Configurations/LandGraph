"""Docker container lifecycle management using aiodocker."""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator, Optional

import aiodocker

from core.config import settings

log = logging.getLogger(__name__)


class DockerManager:
    """Manages ephemeral agent containers."""

    def __init__(self) -> None:
        self._docker: Optional[aiodocker.Docker] = None

    async def _get_client(self) -> aiodocker.Docker:
        if self._docker is None:
            self._docker = aiodocker.Docker()
        return self._docker

    async def close(self) -> None:
        if self._docker is not None:
            await self._docker.close()
            self._docker = None

    async def create_container(
        self,
        image: str,
        env: dict[str, str],
        volumes: list[str],
        mem_limit: str = "",
        cpu_quota: int = 0,
        name: Optional[str] = None,
    ) -> str:
        """Create a container and return its ID."""
        docker = await self._get_client()
        host_config: dict[str, Any] = {
            "Binds": volumes,
            "NetworkMode": "none",
        }
        if mem_limit:
            host_config["Memory"] = _parse_mem_limit(mem_limit)
        if cpu_quota > 0:
            host_config["CpuQuota"] = cpu_quota

        config: dict[str, Any] = {
            "Image": image,
            "Env": [f"{k}={v}" for k, v in env.items()],
            "OpenStdin": True,
            "StdinOnce": True,
            "Tty": False,
            "HostConfig": host_config,
        }
        container = await docker.containers.create_or_replace(
            name=name or "", config=config
        )
        container_id = container.id
        log.info("Container created", extra={"container_id": container_id[:12], "image": image})
        return container_id

    async def start_container(self, container_id: str) -> None:
        """Start a container."""
        docker = await self._get_client()
        container = await docker.containers.get(container_id)
        await container.start()
        log.info("Container started", extra={"container_id": container_id[:12]})

    async def attach_stdin(self, container_id: str) -> Any:
        """Attach to container stdin and return the websocket stream."""
        docker = await self._get_client()
        container = await docker.containers.get(container_id)
        ws = await container.websocket(stdin=True, stdout=False, stderr=False, stream=True)
        return ws

    async def read_stdout(self, container_id: str) -> AsyncIterator[bytes]:
        """Read stdout from a container as an async iterator of lines."""
        docker = await self._get_client()
        container = await docker.containers.get(container_id)
        stream = container.log(stdout=True, stderr=False, follow=True)
        async for line in stream:
            yield line.encode() if isinstance(line, str) else line

    async def stop_container(self, container_id: str, timeout: int = 10) -> None:
        """Stop a container. Force kill after timeout."""
        docker = await self._get_client()
        try:
            container = await docker.containers.get(container_id)
            await container.stop(t=timeout)
            log.info("Container stopped", extra={"container_id": container_id[:12]})
        except aiodocker.exceptions.DockerError as e:
            if e.status == 304:  # already stopped
                pass
            elif e.status == 404:
                log.warning("Container not found for stop", extra={"container_id": container_id[:12]})
            else:
                raise

    async def remove_container(self, container_id: str) -> None:
        """Remove a container, force if needed."""
        docker = await self._get_client()
        try:
            container = await docker.containers.get(container_id)
            await container.delete(force=True)
            log.info("Container removed", extra={"container_id": container_id[:12]})
        except aiodocker.exceptions.DockerError as e:
            if e.status == 404:
                log.warning("Container not found for removal", extra={"container_id": container_id[:12]})
            else:
                raise

    async def get_logs(self, container_id: str, tail: int = 200) -> str:
        """Get stderr logs from a container."""
        docker = await self._get_client()
        try:
            container = await docker.containers.get(container_id)
            logs = await container.log(stdout=False, stderr=True, tail=tail)
            return "".join(logs)
        except aiodocker.exceptions.DockerError:
            return ""

    async def wait_container(self, container_id: str) -> int:
        """Wait for a container to exit. Return exit code."""
        docker = await self._get_client()
        container = await docker.containers.get(container_id)
        result = await container.wait()
        return result.get("StatusCode", -1)

    @asynccontextmanager
    async def managed_container(
        self,
        image: str,
        env: dict[str, str],
        volumes: list[str],
        mem_limit: str = "",
        cpu_quota: int = 0,
        name: Optional[str] = None,
    ) -> AsyncIterator[str]:
        """Context manager that guarantees cleanup."""
        container_id = await self.create_container(
            image=image,
            env=env,
            volumes=volumes,
            mem_limit=mem_limit,
            cpu_quota=cpu_quota,
            name=name,
        )
        try:
            yield container_id
        finally:
            try:
                await self.stop_container(container_id, timeout=5)
            except Exception as e:
                log.warning("Error stopping container", extra={"error": str(e)})
            try:
                await self.remove_container(container_id)
            except Exception as e:
                log.warning("Error removing container", extra={"error": str(e)})


def _parse_mem_limit(limit: str) -> int:
    """Parse '2g' → bytes."""
    limit = limit.strip().lower()
    multipliers = {"b": 1, "k": 1024, "m": 1024**2, "g": 1024**3}
    if limit[-1] in multipliers:
        return int(limit[:-1]) * multipliers[limit[-1]]
    return int(limit)
