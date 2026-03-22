"""Tests for routes/deliverables.py — deliverable CRUD endpoints."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient

from core.security import encode_token
from schemas.deliverable import (
    DeliverableDetail,
    DeliverableResponse,
    RemarkResponse,
)
from tests.conftest import SAMPLE_USER_ID

TOKEN = encode_token(str(SAMPLE_USER_ID), "alice@t.com", "member", ["team1"])
HEADERS = {"Authorization": f"Bearer {TOKEN}"}

NOW = datetime(2026, 3, 20, tzinfo=timezone.utc)


def _deliverable(**kw) -> DeliverableResponse:
    defaults = dict(
        id=1, task_id="aaa", key="prd", deliverable_type="DOC",
        file_path="a.md", git_branch="temp/prd", category="docs",
        status="pending", reviewer=None, review_comment=None,
        reviewed_at=None, created_at=NOW, agent_id="analyst",
        phase="Discovery", project_slug="demo",
    )
    defaults.update(kw)
    return DeliverableResponse(**defaults)


def _detail(**kw) -> DeliverableDetail:
    d = dict(
        id=1, task_id="aaa", key="prd", deliverable_type="DOC",
        file_path="a.md", git_branch="temp/prd", category="docs",
        status="pending", reviewer=None, review_comment=None,
        reviewed_at=None, created_at=NOW, agent_id="analyst",
        phase="Discovery", project_slug="demo",
        content="# PRD", cost_usd=0.05,
    )
    d.update(kw)
    return DeliverableDetail(**d)


def _remark(**kw) -> RemarkResponse:
    defaults = dict(id=10, artifact_id=1, reviewer="alice@t.com", comment="OK", created_at=NOW)
    defaults.update(kw)
    return RemarkResponse(**defaults)


# ── GET /api/projects/{slug}/deliverables ────────────────────

@pytest.mark.asyncio
async def test_list_deliverables_200(app_client: AsyncClient):
    items = [_deliverable(id=1), _deliverable(id=2, key="specs")]
    with patch("routes.deliverables.deliverable_service.list_deliverables", new_callable=AsyncMock, return_value=items):
        resp = await app_client.get("/api/projects/demo/deliverables", headers=HEADERS)
    assert resp.status_code == 200
    assert len(resp.json()) == 2


# ── GET /api/deliverables/{id} ───────────────────────────────

@pytest.mark.asyncio
async def test_get_deliverable_200(app_client: AsyncClient):
    with patch("routes.deliverables.deliverable_service.get_deliverable", new_callable=AsyncMock, return_value=_detail()):
        resp = await app_client.get("/api/deliverables/1", headers=HEADERS)
    assert resp.status_code == 200
    assert resp.json()["content"] == "# PRD"


@pytest.mark.asyncio
async def test_get_deliverable_404(app_client: AsyncClient):
    with patch("routes.deliverables.deliverable_service.get_deliverable", new_callable=AsyncMock, return_value=None):
        resp = await app_client.get("/api/deliverables/999", headers=HEADERS)
    assert resp.status_code == 404


# ── POST /api/deliverables/{id}/validate ─────────────────────

@pytest.mark.asyncio
async def test_validate_approve_200(app_client: AsyncClient):
    with patch("routes.deliverables.deliverable_service.validate_deliverable", new_callable=AsyncMock, return_value=True):
        resp = await app_client.post(
            "/api/deliverables/1/validate",
            json={"verdict": "approved", "comment": "LGTM"},
            headers=HEADERS,
        )
    assert resp.status_code == 200
    assert resp.json()["verdict"] == "approved"


@pytest.mark.asyncio
async def test_validate_reject_200(app_client: AsyncClient):
    with patch("routes.deliverables.deliverable_service.validate_deliverable", new_callable=AsyncMock, return_value=True):
        resp = await app_client.post(
            "/api/deliverables/1/validate",
            json={"verdict": "rejected", "comment": "Needs work"},
            headers=HEADERS,
        )
    assert resp.status_code == 200
    assert resp.json()["verdict"] == "rejected"


# ── POST /api/deliverables/{id}/remark ───────────────────────

@pytest.mark.asyncio
async def test_submit_remark_200(app_client: AsyncClient):
    with patch("routes.deliverables.deliverable_service.submit_remark", new_callable=AsyncMock, return_value=_remark()):
        resp = await app_client.post(
            "/api/deliverables/1/remark",
            json={"comment": "OK"},
            headers=HEADERS,
        )
    assert resp.status_code == 200
    assert resp.json()["comment"] == "OK"


# ── GET /api/deliverables/{id}/remarks ───────────────────────

@pytest.mark.asyncio
async def test_list_remarks_200(app_client: AsyncClient):
    items = [_remark(id=10), _remark(id=11, comment="Fix")]
    with patch("routes.deliverables.deliverable_service.list_remarks", new_callable=AsyncMock, return_value=items):
        resp = await app_client.get("/api/deliverables/1/remarks", headers=HEADERS)
    assert resp.status_code == 200
    assert len(resp.json()) == 2


# ── GET /api/projects/{slug}/branches ────────────────────────

@pytest.mark.asyncio
async def test_list_branches_200(app_client: AsyncClient):
    with (
        patch("routes.deliverables.os.path.isdir", return_value=True),
        patch("routes.deliverables._run_git", new_callable=AsyncMock, side_effect=[
            (0, "temp/prd\nmain\ntemp/specs\n", ""),
            (0, "Add PRD", ""),
            (0, "Add specs", ""),
        ]),
    ):
        resp = await app_client.get("/api/projects/demo/branches", headers=HEADERS)
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 2
    assert data[0]["name"] == "temp/prd"
