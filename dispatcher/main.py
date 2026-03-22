"""Dispatcher service — FastAPI application."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import Optional

import structlog
from fastapi import FastAPI

from core.channels import CH_HITL_RESPONSE
from core.config import settings
from core.database import init_pool, close_pool, get_pool
from core.events import HitlResponseWaiter, PgNotifyListener
from routes.health import router as health_router
from routes.tasks import router as tasks_router
from routes.internal import router as internal_router
from services.artifact_store import ArtifactStore
from services.cost_tracker import CostTracker
from services.docker_manager import DockerManager
from services.hitl_bridge import HitlBridge
from services.task_runner import TaskRunner

# ── Logging setup (structlog JSON) ──────────────────

structlog.configure(
    processors=[
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.JSONRenderer(),
    ],
    wrapper_class=structlog.stdlib.BoundLogger,
    logger_factory=structlog.stdlib.LoggerFactory(),
)

log = structlog.get_logger(__name__)

# ── Singletons ──────────────────────────────────────

_docker_manager: Optional[DockerManager] = None
_task_runner: Optional[TaskRunner] = None
_notify_listener: Optional[PgNotifyListener] = None
_hitl_waiter: Optional[HitlResponseWaiter] = None


def get_task_runner() -> TaskRunner:
    if _task_runner is None:
        raise RuntimeError("TaskRunner not initialised")
    return _task_runner


# ── Lifespan ────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    global _docker_manager, _task_runner, _notify_listener, _hitl_waiter

    log.info("dispatcher_starting")
    pool = await init_pool()

    # Docker manager
    _docker_manager = DockerManager()

    # PG NOTIFY listener for HITL responses
    _hitl_waiter = HitlResponseWaiter()
    _notify_listener = PgNotifyListener()
    _notify_listener.on(CH_HITL_RESPONSE, _hitl_waiter.handle_response)
    await _notify_listener.start([CH_HITL_RESPONSE])

    # Services
    hitl = HitlBridge(pool, _hitl_waiter)
    artifacts = ArtifactStore(pool)
    costs = CostTracker(pool)
    _task_runner = TaskRunner(pool, _docker_manager, hitl, artifacts, costs)

    log.info("dispatcher_ready", port=settings.dispatcher_port)
    yield

    log.info("dispatcher_stopping")
    if _notify_listener:
        await _notify_listener.stop()
    if _docker_manager:
        await _docker_manager.close()
    await close_pool()
    _task_runner = None
    _docker_manager = None
    log.info("dispatcher_stopped")


# ── App ─────────────────────────────────────────────

app = FastAPI(
    title="ag.flow Dispatcher",
    version="0.1.0",
    lifespan=lifespan,
)

app.include_router(health_router)
app.include_router(tasks_router, prefix="/api")
app.include_router(internal_router, prefix="/api")
