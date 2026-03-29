"""Docker log streaming routes (SSE)."""

from __future__ import annotations

import asyncio
from typing import Optional
from uuid import UUID

import structlog
from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from jose import JWTError

from core.security import TokenData, decode_token, get_current_user

log = structlog.get_logger(__name__)

router = APIRouter(tags=["logs"])

ALLOWED_CONTAINERS: list[str] = sorted([
    "langgraph-hitl",
    "langgraph-api",
    "langgraph-admin",
    "langgraph-dispatcher",
    "langgraph-discord",
    "langgraph-mail",
])


async def _resolve_user(
    request: Request,
    token: Optional[str] = None,
) -> TokenData:
    """Resolve user from Authorization header or fallback query token."""
    # 1. Try Authorization header
    try:
        return await get_current_user(request)
    except HTTPException:
        pass

    # 2. Fallback: query param token (EventSource cannot send headers)
    if token:
        try:
            payload = decode_token(token)
            return TokenData(
                user_id=UUID(payload["sub"]),
                email=payload.get("email", ""),
                role=payload.get("role", "member"),
                teams=payload.get("teams", []),
                culture=payload.get("culture", "fr"),
            )
        except (JWTError, KeyError, ValueError):
            raise HTTPException(status_code=401, detail="auth.invalid_token")

    raise HTTPException(status_code=401, detail="auth.missing_token")


def _require_admin(user: TokenData) -> None:
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="auth.admin_required")


@router.get("/api/logs/containers")
async def list_containers(request: Request) -> list[str]:
    """Return sorted list of allowed container names."""
    await get_current_user(request)
    return ALLOWED_CONTAINERS


@router.get("/api/logs/stream")
async def stream_logs(
    request: Request,
    container: str = Query(..., description="Docker container name"),
    tail: int = Query(200, ge=1, le=10000, description="Number of initial lines"),
    token: Optional[str] = Query(None, description="JWT token fallback for EventSource"),
) -> StreamingResponse:
    """Stream Docker container logs via SSE (admin only)."""
    await _resolve_user(request, token)

    if container not in ALLOWED_CONTAINERS:
        raise HTTPException(status_code=400, detail="logs.container_not_allowed")

    tail_str = str(tail)

    async def _generate():
        proc: Optional[asyncio.subprocess.Process] = None
        try:
            proc = await asyncio.create_subprocess_exec(
                "docker", "logs", "-f", "--timestamps", "--tail", tail_str, container,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
            )
            assert proc.stdout is not None
            while True:
                line = await proc.stdout.readline()
                if not line:
                    break
                text = line.decode("utf-8", errors="replace").rstrip("\n")
                yield f"data: {text}\n\n"
        except asyncio.CancelledError:
            log.debug("log_stream_cancelled", container=container)
        except Exception as exc:
            log.error("log_stream_error", container=container, error=str(exc))
            yield f"event: error\ndata: {exc}\n\n"
        finally:
            if proc is not None:
                try:
                    proc.terminate()
                    try:
                        await asyncio.wait_for(proc.wait(), timeout=5.0)
                    except asyncio.TimeoutError:
                        proc.kill()
                        await proc.wait()
                except ProcessLookupError:
                    pass
                log.debug("log_stream_closed", container=container)

    return StreamingResponse(
        _generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
