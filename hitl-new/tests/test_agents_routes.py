"""Tests for routes/agents.py — list agents with pending counts."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient

from core.security import encode_token
from tests.conftest import SAMPLE_USER_ID, make_record

MEMBER_TOKEN = encode_token(str(SAMPLE_USER_ID), "m@t.com", "member", ["team1"])
HEADERS = {"Authorization": f"Bearer {MEMBER_TOKEN}"}

FAKE_REGISTRY = {
    "agents": {
        "orchestrator": {"name": "Orchestrator", "llm": "claude-sonnet", "type": "orchestrator"},
        "lead_dev": {"name": "Lead Dev", "llm": "claude-sonnet", "type": "lead"},
    },
}


# ── GET /api/teams/{id}/agents ───────────────────────────────

@pytest.mark.asyncio
async def test_list_agents_200(app_client: AsyncClient, mock_pool: AsyncMock):
    mock_pool.fetchrow.return_value = make_record(cnt=2)

    with patch("routes.agents._load_agents_registry", return_value=FAKE_REGISTRY):
        resp = await app_client.get("/api/teams/team1/agents", headers=HEADERS)

    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 2
    names = {a["name"] for a in data}
    assert "Lead Dev" in names
    assert data[0]["pending_questions"] == 2


@pytest.mark.asyncio
async def test_list_agents_empty_registry_404(app_client: AsyncClient):
    with patch("routes.agents._load_agents_registry", return_value={}):
        resp = await app_client.get("/api/teams/team1/agents", headers=HEADERS)
    assert resp.status_code == 404
    assert "registry" in resp.json()["detail"]
