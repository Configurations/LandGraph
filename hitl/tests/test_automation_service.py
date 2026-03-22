"""Tests for services/automation_service.py — rules, confidence, auto-approve."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest

from tests.conftest import FakeRecord, make_record


NOW = datetime(2026, 3, 22, 12, 0, tzinfo=timezone.utc)


def _rule_row(**overrides) -> FakeRecord:
    """Build a fake automation_rules row."""
    defaults = dict(
        id=1,
        project_slug="tracker",
        workflow_type="discovery",
        deliverable_type="document",
        auto_approve=True,
        confidence_threshold=0.8,
        min_approved_history=5,
        created_at=NOW,
    )
    defaults.update(overrides)
    return make_record(**defaults)


def _confidence_row(total=10, approved=8, rejected=2) -> FakeRecord:
    return make_record(total=total, approved=approved, rejected=rejected)


# ── check_auto_approve ───────────────────────────────────────


@pytest.mark.asyncio
@patch("services.automation_service.get_agent_confidence", new_callable=AsyncMock)
@patch("services.automation_service._find_matching_rule", new_callable=AsyncMock)
@patch("services.automation_service.fetch_one", new_callable=AsyncMock)
async def test_check_auto_approve_true(mock_fetch, mock_rule, mock_conf):
    """check_auto_approve returns True when rule matches and confidence is high."""
    mock_fetch.return_value = make_record(
        deliverable_type="document", agent_id="analyst",
        project_slug="tracker", workflow_type="discovery",
    )
    mock_rule.return_value = make_record(
        auto_approve=True, confidence_threshold=0.7, min_approved_history=3,
    )
    from schemas.automation import AgentConfidenceResponse
    mock_conf.return_value = AgentConfidenceResponse(
        agent_id="analyst", total=10, approved=9, rejected=1, confidence=0.9,
    )

    from services.automation_service import check_auto_approve

    result = await check_auto_approve(42)
    assert result is True


@pytest.mark.asyncio
@patch("services.automation_service.get_agent_confidence", new_callable=AsyncMock)
@patch("services.automation_service._find_matching_rule", new_callable=AsyncMock)
@patch("services.automation_service.fetch_one", new_callable=AsyncMock)
async def test_check_auto_approve_below_threshold(mock_fetch, mock_rule, mock_conf):
    """check_auto_approve returns False when confidence is below threshold."""
    mock_fetch.return_value = make_record(
        deliverable_type="document", agent_id="analyst",
        project_slug="tracker", workflow_type="discovery",
    )
    mock_rule.return_value = make_record(
        auto_approve=True, confidence_threshold=0.9, min_approved_history=3,
    )
    from schemas.automation import AgentConfidenceResponse
    mock_conf.return_value = AgentConfidenceResponse(
        agent_id="analyst", total=10, approved=5, rejected=5, confidence=0.5,
    )

    from services.automation_service import check_auto_approve

    result = await check_auto_approve(42)
    assert result is False


@pytest.mark.asyncio
@patch("services.automation_service._find_matching_rule", new_callable=AsyncMock)
@patch("services.automation_service.fetch_one", new_callable=AsyncMock)
async def test_check_auto_approve_no_rule_stays_pending(mock_fetch, mock_rule):
    """check_auto_approve returns False when no matching rule exists."""
    mock_fetch.return_value = make_record(
        deliverable_type="document", agent_id="analyst",
        project_slug="tracker", workflow_type="discovery",
    )
    mock_rule.return_value = None

    from services.automation_service import check_auto_approve

    result = await check_auto_approve(42)
    assert result is False


# ── get_agent_confidence ─────────────────────────────────────


@pytest.mark.asyncio
@patch("services.automation_service.fetch_one", new_callable=AsyncMock)
async def test_get_agent_confidence_calculates_correctly(mock_fetch):
    """get_agent_confidence computes ratio from approval history."""
    mock_fetch.return_value = _confidence_row(total=20, approved=18, rejected=2)

    from services.automation_service import get_agent_confidence

    result = await get_agent_confidence("analyst", "document")

    assert result.agent_id == "analyst"
    assert result.total == 20
    assert result.approved == 18
    assert result.confidence == 0.9


@pytest.mark.asyncio
@patch("services.automation_service.fetch_one", new_callable=AsyncMock)
async def test_get_agent_confidence_zero_history(mock_fetch):
    """get_agent_confidence returns 0.0 when no history."""
    mock_fetch.return_value = _confidence_row(total=0, approved=0, rejected=0)

    from services.automation_service import get_agent_confidence

    result = await get_agent_confidence("analyst")
    assert result.confidence == 0.0
    assert result.total == 0


# ── list_rules ───────────────────────────────────────────────


@pytest.mark.asyncio
@patch("services.automation_service.fetch_all", new_callable=AsyncMock)
async def test_list_rules_returns_filtered(mock_fetch_all):
    """list_rules returns rules filtered by project_slug."""
    mock_fetch_all.return_value = [_rule_row(id=1), _rule_row(id=2)]

    from services.automation_service import list_rules

    result = await list_rules("tracker")
    assert len(result) == 2
    assert result[0].id == 1


# ── create_rule ──────────────────────────────────────────────


@pytest.mark.asyncio
@patch("services.automation_service.fetch_one", new_callable=AsyncMock)
async def test_create_rule_inserts(mock_fetch):
    """create_rule inserts a new automation rule."""
    mock_fetch.return_value = _rule_row(id=10)

    from schemas.automation import AutomationRuleCreate
    from services.automation_service import create_rule

    data = AutomationRuleCreate(
        project_slug="tracker",
        deliverable_type="document",
        auto_approve=True,
        confidence_threshold=0.8,
    )
    result = await create_rule(data)

    assert result.id == 10
    assert result.auto_approve is True
    mock_fetch.assert_awaited_once()


# ── get_automation_stats ─────────────────────────────────────


@pytest.mark.asyncio
@patch("services.automation_service.fetch_one", new_callable=AsyncMock)
async def test_get_automation_stats_returns_percentages(mock_fetch):
    """get_automation_stats computes correct percentage breakdowns."""
    mock_fetch.return_value = make_record(
        total_reviewed=100, auto_approved=60, manual_approved=30, rejected=10,
    )

    from services.automation_service import get_automation_stats

    result = await get_automation_stats("tracker")

    assert result.total_reviewed == 100
    assert result.auto_approved == 60
    assert result.auto_pct == 60.0
    assert result.manual_pct == 30.0
    assert result.rejected_pct == 10.0
