"""Tests for routes/relations.py — HTTP layer."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient

from core.security import encode_token
from tests.conftest import SAMPLE_USER_ID


NOW = datetime(2026, 3, 22, 12, 0, tzinfo=timezone.utc)

TOKEN = encode_token(str(SAMPLE_USER_ID), "alice@test.com", "member", ["team1"])
AUTH = {"Authorization": f"Bearer {TOKEN}"}


# ── POST /api/pm/issues/{id}/relations ────────────────────────

@pytest.mark.asyncio
@patch("services.relation_service.create_relation", new_callable=AsyncMock)
async def test_create_relation_201(mock_create, app_client: AsyncClient):
    from schemas.issue import RelationResponse

    mock_create.return_value = RelationResponse(
        id=1, type="blocks", direction="outgoing", display_type="Blocks",
        issue_id="TEAM-002", issue_title="Backend", issue_status="todo",
        reason="dep", created_by="alice@test.com", created_at=NOW,
    )

    resp = await app_client.post(
        "/api/pm/issues/TEAM-001/relations",
        json={"type": "blocks", "target_issue_id": "TEAM-002", "reason": "dep"},
        headers=AUTH,
    )
    assert resp.status_code == 201
    assert resp.json()["type"] == "blocks"


@pytest.mark.asyncio
@patch("services.relation_service.create_relation", new_callable=AsyncMock)
async def test_create_relation_self_ref_400(mock_create, app_client: AsyncClient):
    mock_create.side_effect = ValueError("issue.self_relation")

    resp = await app_client.post(
        "/api/pm/issues/TEAM-001/relations",
        json={"type": "blocks", "target_issue_id": "TEAM-001"},
        headers=AUTH,
    )
    assert resp.status_code == 400


# ── GET /api/pm/issues/{id}/relations ─────────────────────────

@pytest.mark.asyncio
@patch("services.relation_service.list_relations", new_callable=AsyncMock)
async def test_list_relations_200(mock_list, app_client: AsyncClient):
    from schemas.issue import RelationResponse

    mock_list.return_value = [
        RelationResponse(
            id=1, type="blocks", direction="outgoing", display_type="Blocks",
            issue_id="TEAM-002", created_by="alice@test.com", created_at=NOW,
        ),
    ]

    resp = await app_client.get("/api/pm/issues/TEAM-001/relations", headers=AUTH)
    assert resp.status_code == 200
    assert len(resp.json()) == 1


# ── DELETE /api/pm/relations/{id} ─────────────────────────────

@pytest.mark.asyncio
@patch("services.relation_service.delete_relation", new_callable=AsyncMock)
async def test_delete_relation_204(mock_del, app_client: AsyncClient):
    mock_del.return_value = True

    resp = await app_client.delete("/api/pm/relations/1", headers=AUTH)
    assert resp.status_code == 204


@pytest.mark.asyncio
@patch("services.relation_service.delete_relation", new_callable=AsyncMock)
async def test_delete_relation_404(mock_del, app_client: AsyncClient):
    mock_del.return_value = False

    resp = await app_client.delete("/api/pm/relations/999", headers=AUTH)
    assert resp.status_code == 404
