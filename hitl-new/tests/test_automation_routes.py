"""Tests for routes/automation.py — automation rules HTTP layer."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient

from core.security import encode_token
from tests.conftest import SAMPLE_USER_ID


TOKEN = encode_token(str(SAMPLE_USER_ID), "alice@test.com", "member", ["team1"])
AUTH = {"Authorization": f"Bearer {TOKEN}"}
NOW = datetime(2026, 3, 22, tzinfo=timezone.utc)


def _rule_response(**overrides):
    from schemas.automation import AutomationRuleResponse
    defaults = dict(
        id=1, project_slug="tracker", workflow_type="discovery",
        deliverable_type="document", auto_approve=True,
        confidence_threshold=0.8, min_approved_history=5, created_at=NOW,
    )
    defaults.update(overrides)
    return AutomationRuleResponse(**defaults)


# ── GET /api/automation/rules ────────────────────────────────


@pytest.mark.asyncio
@patch("routes.automation.automation_service.list_rules", new_callable=AsyncMock)
async def test_list_rules_200(mock_list, app_client: AsyncClient):
    """GET /api/automation/rules returns 200 with a list."""
    mock_list.return_value = [_rule_response()]

    resp = await app_client.get("/api/automation/rules", headers=AUTH)
    assert resp.status_code == 200
    assert len(resp.json()) == 1


# ── POST /api/automation/rules ───────────────────────────────


@pytest.mark.asyncio
@patch("routes.automation.automation_service.create_rule", new_callable=AsyncMock)
async def test_create_rule_201(mock_create, app_client: AsyncClient):
    """POST /api/automation/rules returns 201."""
    mock_create.return_value = _rule_response(id=10)

    resp = await app_client.post(
        "/api/automation/rules", headers=AUTH,
        json={"deliverable_type": "document", "auto_approve": True},
    )
    assert resp.status_code == 201
    assert resp.json()["id"] == 10


# ── PUT /api/automation/rules/{id} ───────────────────────────


@pytest.mark.asyncio
@patch("routes.automation.automation_service.update_rule", new_callable=AsyncMock)
async def test_update_rule_200(mock_update, app_client: AsyncClient):
    """PUT /api/automation/rules/{id} returns 200."""
    mock_update.return_value = _rule_response(confidence_threshold=0.9)

    resp = await app_client.put(
        "/api/automation/rules/1", headers=AUTH,
        json={"deliverable_type": "document", "confidence_threshold": 0.9},
    )
    assert resp.status_code == 200


# ── DELETE /api/automation/rules/{id} ────────────────────────


@pytest.mark.asyncio
@patch("routes.automation.automation_service.delete_rule", new_callable=AsyncMock)
async def test_delete_rule_200(mock_delete, app_client: AsyncClient):
    """DELETE /api/automation/rules/{id} returns 200."""
    mock_delete.return_value = True

    resp = await app_client.delete("/api/automation/rules/1", headers=AUTH)
    assert resp.status_code == 200
    assert resp.json()["ok"] is True


# ── GET /api/automation/stats ────────────────────────────────


@pytest.mark.asyncio
@patch("routes.automation.automation_service.get_automation_stats", new_callable=AsyncMock)
async def test_get_stats_200(mock_stats, app_client: AsyncClient):
    """GET /api/automation/stats returns 200 with percentages."""
    from schemas.automation import AutomationStatsResponse
    mock_stats.return_value = AutomationStatsResponse(
        total_reviewed=100, auto_approved=60, manual_approved=30, rejected=10,
        auto_pct=60.0, manual_pct=30.0, rejected_pct=10.0,
    )

    resp = await app_client.get(
        "/api/automation/stats?project_slug=tracker", headers=AUTH,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["auto_pct"] == 60.0


# ── GET /api/automation/agent-confidence/{id} ────────────────


@pytest.mark.asyncio
@patch("routes.automation.automation_service.get_agent_confidence", new_callable=AsyncMock)
async def test_get_agent_confidence_200(mock_conf, app_client: AsyncClient):
    """GET /api/automation/agent-confidence/{id} returns 200."""
    from schemas.automation import AgentConfidenceResponse
    mock_conf.return_value = AgentConfidenceResponse(
        agent_id="analyst", total=20, approved=18, rejected=2, confidence=0.9,
    )

    resp = await app_client.get(
        "/api/automation/agent-confidence/analyst", headers=AUTH,
    )
    assert resp.status_code == 200
    assert resp.json()["confidence"] == 0.9
