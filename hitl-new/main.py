"""HITL Console — FastAPI application entry point."""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from typing import AsyncGenerator

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from core.config import load_teams, settings
from core.database import close_pool, execute, fetch_one, init_pool
from core.pg_notify import pg_listener
from core.security import hash_password
from core.websocket_manager import ws_manager

# Configure structlog
structlog.configure(
    processors=[
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.dev.ConsoleRenderer()
        if os.getenv("HITL_DEV")
        else structlog.processors.JSONRenderer(),
    ],
    logger_factory=structlog.PrintLoggerFactory(),
)

log = structlog.get_logger("hitl-console")


async def _ensure_schema() -> None:
    """Ensure culture column and triggers exist."""
    await execute("""
        ALTER TABLE project.hitl_users
        ADD COLUMN IF NOT EXISTS culture TEXT DEFAULT 'fr'
    """)
    await execute("""
        CREATE TABLE IF NOT EXISTS project.hitl_chat_messages (
            id SERIAL PRIMARY KEY,
            team_id TEXT NOT NULL,
            agent_id TEXT NOT NULL,
            thread_id TEXT NOT NULL,
            sender TEXT NOT NULL,
            content TEXT NOT NULL,
            created_at TIMESTAMPTZ DEFAULT NOW()
        )
    """)
    await execute("""
        CREATE INDEX IF NOT EXISTS idx_hitl_chat_thread
        ON project.hitl_chat_messages (team_id, agent_id, thread_id, created_at)
    """)
    # PG NOTIFY triggers
    await execute("""
        CREATE OR REPLACE FUNCTION notify_hitl_request() RETURNS trigger AS $$
        BEGIN
            PERFORM pg_notify('hitl_request', json_build_object(
                'id', NEW.id,
                'team_id', NEW.team_id,
                'agent_id', NEW.agent_id,
                'thread_id', NEW.thread_id,
                'request_type', NEW.request_type,
                'prompt', LEFT(NEW.prompt, 500),
                'status', NEW.status,
                'created_at', NEW.created_at
            )::text);
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql
    """)
    await execute(
        "DROP TRIGGER IF EXISTS hitl_request_notify ON project.hitl_requests"
    )
    await execute("""
        CREATE TRIGGER hitl_request_notify
        AFTER INSERT ON project.hitl_requests
        FOR EACH ROW EXECUTE FUNCTION notify_hitl_request()
    """)
    await execute("""
        CREATE OR REPLACE FUNCTION notify_hitl_chat() RETURNS trigger AS $$
        BEGIN
            PERFORM pg_notify('hitl_chat', json_build_object(
                'id', NEW.id,
                'team_id', NEW.team_id,
                'agent_id', NEW.agent_id,
                'thread_id', NEW.thread_id,
                'sender', NEW.sender,
                'content', LEFT(NEW.content, 4000),
                'created_at', NEW.created_at
            )::text);
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql
    """)
    await execute(
        "DROP TRIGGER IF EXISTS hitl_chat_notify ON project.hitl_chat_messages"
    )
    await execute("""
        CREATE TRIGGER hitl_chat_notify
        AFTER INSERT ON project.hitl_chat_messages
        FOR EACH ROW EXECUTE FUNCTION notify_hitl_chat()
    """)


async def _seed_admin() -> None:
    """Create default admin user if no users exist."""
    email = settings.hitl_admin_email
    password = settings.hitl_admin_password

    row = await fetch_one("SELECT COUNT(*) as cnt FROM project.hitl_users")
    if row and row["cnt"] > 0:
        return

    hashed = hash_password(password)
    new_row = await fetch_one(
        """INSERT INTO project.hitl_users
           (email, password_hash, display_name, role, auth_type, culture)
           VALUES ($1, $2, 'Admin', 'admin', 'local', 'fr')
           RETURNING id""",
        email, hashed,
    )
    if not new_row:
        log.error("seed_admin_failed")
        return

    uid = new_row["id"]
    teams = load_teams()
    for t in teams:
        await execute(
            """INSERT INTO project.hitl_team_members (user_id, team_id, role)
               VALUES ($1, $2, 'admin')
               ON CONFLICT DO NOTHING""",
            uid, t["id"],
        )

    if password == "admin":
        log.critical(
            "SECURITY_RISK_admin_password_is_default",
            msg="Set HITL_ADMIN_PASSWORD env var immediately — password 'admin' is insecure",
            email=email,
        )
    log.info("admin_seeded", email=email, teams=len(teams))


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Startup and shutdown lifecycle."""
    # Startup
    await init_pool()
    await _ensure_schema()
    await _seed_admin()
    await pg_listener.start(ws_manager)
    log.info("hitl_console_started")
    yield
    # Shutdown
    await pg_listener.stop()
    await close_pool()
    log.info("hitl_console_stopped")


app = FastAPI(
    title="HITL Console",
    version="2.0.0",
    lifespan=lifespan,
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount routers
from routes.agents import router as agents_router
from routes.auth import router as auth_router
from routes.chat import router as chat_router
from routes.dashboard import router as dashboard_router
from routes.deliverables import router as deliverables_router
from routes.health import router as health_router
from routes.hitl import router as hitl_router
from routes.internal import router as internal_router
from routes.projects import router as projects_router
from routes.rag import router as rag_router
from routes.teams import router as teams_router
from routes.ws import router as ws_router
from routes.issues import router as issues_router
from routes.relations import router as relations_router
from routes.inbox import router as inbox_router
from routes.activity import router as activity_router
from routes.prs import router as prs_router
from routes.pulse import router as pulse_router
from routes.workflow import router as workflow_router
from routes.workflows import router as workflows_router
from routes.project_types import router as project_types_router
from routes.automation import router as automation_router
from routes.project_detail import router as project_detail_router

app.include_router(health_router)
app.include_router(auth_router)
app.include_router(teams_router)
app.include_router(hitl_router)
app.include_router(projects_router)
app.include_router(rag_router)
app.include_router(internal_router)
app.include_router(deliverables_router)
app.include_router(chat_router)
app.include_router(agents_router)
app.include_router(dashboard_router)
app.include_router(ws_router)
app.include_router(issues_router)
app.include_router(relations_router)
app.include_router(inbox_router)
app.include_router(activity_router)
app.include_router(prs_router)
app.include_router(pulse_router)
app.include_router(workflow_router)
app.include_router(workflows_router)
app.include_router(project_types_router)
app.include_router(automation_router)
app.include_router(project_detail_router)

# Serve static files if directory exists (Docker build)
_static_dir = os.path.join(os.path.dirname(__file__), "static")
if os.path.isdir(_static_dir):
    app.mount("/", StaticFiles(directory=_static_dir, html=True), name="static")
