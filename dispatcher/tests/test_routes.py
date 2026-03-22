"""Tests for routes — tasks, health, and internal endpoints."""

from __future__ import annotations

import json
import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient

from tests.conftest import make_record

TASK_ID = UUID("abcdef01-2345-6789-abcd-ef0123456789")
NOW = datetime(2026, 3, 22, 12, 0, 0, tzinfo=timezone.utc)


# ── Fixtures ─────────────────────────────────────────


@pytest.fixture
def mock_runner():
    runner = AsyncMock()
    runner.create = AsyncMock(return_value=TASK_ID)
    runner.execute_by_id = AsyncMock()
    runner.cancel = AsyncMock(return_value=True)
    return runner


@pytest.fixture
def mock_pool_for_routes():
    pool = AsyncMock()
    pool.fetchrow = AsyncMock(return_value=None)
    pool.fetch = AsyncMock(return_value=[])
    pool.fetchval = AsyncMock(return_value=1)

    conn = AsyncMock()
    conn.fetchval = AsyncMock(return_value=1)
    ctx = AsyncMock()
    ctx.__aenter__ = AsyncMock(return_value=conn)
    ctx.__aexit__ = AsyncMock(return_value=False)
    pool.acquire = MagicMock(return_value=ctx)

    return pool


@pytest.fixture
def app(mock_runner, mock_pool_for_routes):
    """Build a FastAPI app with mocked dependencies."""
    from routes.tasks import router as tasks_router
    from routes.health import router as health_router
    from routes.internal import router as internal_router

    app = FastAPI()
    app.include_router(tasks_router, prefix="/api")
    app.include_router(health_router)
    app.include_router(internal_router, prefix="/api")

    with patch("routes.tasks._get_runner", return_value=mock_runner), \
         patch("routes.tasks.get_pool", return_value=mock_pool_for_routes), \
         patch("routes.health.get_pool", return_value=mock_pool_for_routes), \
         patch("routes.internal.get_pool", return_value=mock_pool_for_routes):
        yield app, mock_runner, mock_pool_for_routes


@pytest.fixture
def client(app):
    app_instance, _, _ = app
    return TestClient(app_instance)


# ── POST /api/tasks/run ──────────────────────────────


class TestRunTask:
    def test_run_returns_202(self, app, run_task_request_dict):
        app_instance, mock_runner, mock_pool = app
        with patch("routes.tasks._get_runner", return_value=mock_runner), \
             patch("routes.tasks.get_pool", return_value=mock_pool):
            client = TestClient(app_instance)
            resp = client.post("/api/tasks/run", json=run_task_request_dict)
        assert resp.status_code == 202
        data = resp.json()
        assert data["task_id"] == str(TASK_ID)
        assert data["status"] == "pending"

    def test_run_missing_fields_returns_422(self, app):
        app_instance, mock_runner, mock_pool = app
        with patch("routes.tasks._get_runner", return_value=mock_runner), \
             patch("routes.tasks.get_pool", return_value=mock_pool):
            client = TestClient(app_instance)
            resp = client.post("/api/tasks/run", json={"agent_id": "x"})
        assert resp.status_code == 422


# ── GET /api/tasks/{id} ─────────────────────────────


class TestGetTask:
    def test_get_task_not_found(self, app):
        app_instance, mock_runner, mock_pool = app
        mock_pool.fetchrow = AsyncMock(return_value=None)
        with patch("routes.tasks._get_runner", return_value=mock_runner), \
             patch("routes.tasks.get_pool", return_value=mock_pool):
            client = TestClient(app_instance)
            resp = client.get(f"/api/tasks/{TASK_ID}")
        assert resp.status_code == 404

    def test_get_task_found(self, app):
        app_instance, mock_runner, mock_pool = app
        mock_pool.fetchrow = AsyncMock(return_value=make_record(
            id=TASK_ID,
            status="success",
            agent_id="lead_dev",
            team_id="team1",
            project_slug="perf-tracker",
            phase="build",
            cost_usd=0.05,
            created_at=NOW,
            started_at=NOW,
            completed_at=NOW,
            error_message=None,
        ))
        mock_pool.fetch = AsyncMock(return_value=[])

        with patch("routes.tasks._get_runner", return_value=mock_runner), \
             patch("routes.tasks.get_pool", return_value=mock_pool):
            client = TestClient(app_instance)
            resp = client.get(f"/api/tasks/{TASK_ID}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["task_id"] == str(TASK_ID)
        assert data["status"] == "success"
        assert data["events"] == []
        assert data["artifacts"] == []


# ── POST /api/tasks/{id}/cancel ──────────────────────


class TestCancelTask:
    def test_cancel_success(self, app):
        app_instance, mock_runner, mock_pool = app
        mock_runner.cancel = AsyncMock(return_value=True)
        with patch("routes.tasks._get_runner", return_value=mock_runner), \
             patch("routes.tasks.get_pool", return_value=mock_pool):
            client = TestClient(app_instance)
            resp = client.post(f"/api/tasks/{TASK_ID}/cancel")
        assert resp.status_code == 200
        assert resp.json()["status"] == "cancelled"

    def test_cancel_not_cancellable(self, app):
        app_instance, mock_runner, mock_pool = app
        mock_runner.cancel = AsyncMock(return_value=False)
        with patch("routes.tasks._get_runner", return_value=mock_runner), \
             patch("routes.tasks.get_pool", return_value=mock_pool):
            client = TestClient(app_instance)
            resp = client.post(f"/api/tasks/{TASK_ID}/cancel")
        assert resp.status_code == 400


# ── GET /health ──────────────────────────────────────


class TestHealth:
    def test_health_ok(self, app):
        app_instance, _, mock_pool = app
        with patch("routes.health.get_pool", return_value=mock_pool):
            client = TestClient(app_instance)
            resp = client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert data["db"] is True

    def test_health_degraded_on_db_failure(self, app):
        app_instance, _, mock_pool = app
        # Make acquire raise
        mock_pool.acquire = MagicMock(side_effect=RuntimeError("no db"))
        with patch("routes.health.get_pool", return_value=mock_pool):
            client = TestClient(app_instance)
            resp = client.get("/health")
        data = resp.json()
        assert data["status"] == "degraded"
        assert data["db"] is False


# ── GET /api/costs/{slug} ────────────────────────────


class TestGetProjectCosts:
    def test_costs_empty(self, app):
        app_instance, _, mock_pool = app
        mock_pool.fetch = AsyncMock(return_value=[])
        with patch("routes.internal.get_pool", return_value=mock_pool):
            client = TestClient(app_instance)
            resp = client.get("/api/costs/perf-tracker")
        assert resp.status_code == 200
        data = resp.json()
        assert data["project_slug"] == "perf-tracker"
        assert data["total_cost_usd"] == 0.0
        assert data["by_phase"] == []

    def test_costs_with_data(self, app):
        app_instance, _, mock_pool = app
        mock_pool.fetch = AsyncMock(return_value=[
            make_record(
                project_slug="perf-tracker",
                team_id="team1",
                phase="build",
                agent_id="lead_dev",
                total_cost_usd=1.5,
                task_count=10,
                avg_cost_per_task=0.15,
            ),
        ])
        with patch("routes.internal.get_pool", return_value=mock_pool):
            client = TestClient(app_instance)
            resp = client.get("/api/costs/perf-tracker")
        data = resp.json()
        assert data["total_cost_usd"] == 1.5
        assert len(data["by_phase"]) == 1


# ── GET /api/tasks/active ────────────────────────────


class TestGetActiveTasks:
    def test_active_empty(self, app):
        app_instance, _, mock_pool = app
        mock_pool.fetch = AsyncMock(return_value=[])
        with patch("routes.internal.get_pool", return_value=mock_pool):
            client = TestClient(app_instance)
            resp = client.get("/api/tasks/active")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_active_with_tasks(self, app):
        app_instance, _, mock_pool = app
        mock_pool.fetch = AsyncMock(return_value=[
            make_record(
                id=TASK_ID,
                status="running",
                agent_id="dev",
                team_id="team1",
                project_slug="proj",
                phase="build",
                cost_usd=0.0,
                created_at=NOW,
                started_at=NOW,
                completed_at=None,
                error_message=None,
            ),
        ])
        with patch("routes.internal.get_pool", return_value=mock_pool):
            client = TestClient(app_instance)
            resp = client.get("/api/tasks/active")
        data = resp.json()
        assert len(data) == 1
        assert data[0]["status"] == "running"
