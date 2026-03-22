"""Tests for services/workflow_service.py — workflow visualization."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tests.conftest import make_record


SAMPLE_WORKFLOW = {
    "phases": [
        {
            "id": "discovery",
            "name": "Discovery",
            "deliverables": [
                {"key": "prd", "agent": "requirements_analyst", "deliverable_type": "document"},
                {"key": "legal_review", "agent": "legal_advisor", "deliverable_type": "document"},
            ],
        },
        {
            "id": "design",
            "name": "Design",
            "deliverables": [
                {"key": "wireframes", "agent": "ux_designer", "deliverable_type": "design"},
            ],
        },
    ],
}

SAMPLE_REGISTRY = {
    "agents": {
        "requirements_analyst": {"name": "Requirements Analyst"},
        "legal_advisor": {"name": "Legal Advisor"},
        "ux_designer": {"name": "UX Designer"},
    },
}


# ── get_workflow_status ──────────────────────────────────────


@pytest.mark.asyncio
@patch("services.workflow_service._resolve_deliverable_status", new_callable=AsyncMock)
@patch("services.workflow_service._resolve_agent_status", new_callable=AsyncMock)
@patch("services.workflow_service._read_registry_json")
@patch("services.workflow_service._read_workflow_json")
async def test_get_workflow_status_returns_phases(
    mock_wf, mock_reg, mock_agent_status, mock_deliv_status,
):
    """get_workflow_status returns phases with correct statuses."""
    mock_wf.return_value = SAMPLE_WORKFLOW
    mock_reg.return_value = SAMPLE_REGISTRY["agents"]
    mock_agent_status.return_value = ("completed", "task-1")
    mock_deliv_status.return_value = ("completed", 42)

    from services.workflow_service import get_workflow_status

    result = await get_workflow_status("tracker", "team1")

    assert len(result.phases) == 2
    assert result.phases[0].id == "discovery"
    assert result.phases[0].name == "Discovery"
    assert result.total_phases == 2
    # Both agents completed -> phase completed
    assert result.phases[0].status == "completed"
    assert result.completed_phases == 2


# ── get_phase_detail ─────────────────────────────────────────


@pytest.mark.asyncio
@patch("services.workflow_service._resolve_deliverable_status", new_callable=AsyncMock)
@patch("services.workflow_service._resolve_agent_status", new_callable=AsyncMock)
@patch("services.workflow_service._read_registry_json")
@patch("services.workflow_service._read_workflow_json")
async def test_get_phase_detail_returns_agents_and_deliverables(
    mock_wf, mock_reg, mock_agent_status, mock_deliv_status,
):
    """get_phase_detail returns agents and deliverables for a phase."""
    mock_wf.return_value = SAMPLE_WORKFLOW
    mock_reg.return_value = SAMPLE_REGISTRY["agents"]
    mock_agent_status.return_value = ("active", "task-2")
    mock_deliv_status.return_value = ("in_progress", 10)

    from services.workflow_service import get_phase_detail

    result = await get_phase_detail("tracker", "team1", "discovery")

    assert result is not None
    assert result.id == "discovery"
    assert len(result.agents) == 2
    assert result.agents[0].agent_id == "requirements_analyst"
    assert result.agents[0].name == "Requirements Analyst"
    assert result.agents[0].status == "active"
    assert len(result.deliverables) == 2
    assert result.deliverables[0].key == "prd"


@pytest.mark.asyncio
@patch("services.workflow_service._resolve_deliverable_status", new_callable=AsyncMock)
@patch("services.workflow_service._resolve_agent_status", new_callable=AsyncMock)
@patch("services.workflow_service._read_registry_json")
@patch("services.workflow_service._read_workflow_json")
async def test_get_phase_detail_missing_phase_returns_none(
    mock_wf, mock_reg, mock_agent_status, mock_deliv_status,
):
    """get_phase_detail returns None for a non-existent phase."""
    mock_wf.return_value = SAMPLE_WORKFLOW
    mock_reg.return_value = SAMPLE_REGISTRY["agents"]
    mock_agent_status.return_value = ("pending", None)
    mock_deliv_status.return_value = ("pending", None)

    from services.workflow_service import get_phase_detail

    result = await get_phase_detail("tracker", "team1", "nonexistent")
    assert result is None


# ── missing workflow.json ────────────────────────────────────


@pytest.mark.asyncio
@patch("services.workflow_service._read_workflow_json")
async def test_get_workflow_status_missing_json(mock_wf):
    """get_workflow_status returns empty when Workflow.json not found."""
    mock_wf.return_value = None

    from services.workflow_service import get_workflow_status

    result = await get_workflow_status("tracker", "team1")
    assert result.phases == []
    assert result.total_phases == 0
    assert result.completed_phases == 0


# ── _determine_phase_status ──────────────────────────────────


class TestDeterminePhaseStatus:
    def test_all_pending(self):
        from schemas.workflow import PhaseAgent
        from services.workflow_service import _determine_phase_status

        agents = [PhaseAgent(agent_id="a", status="pending")]
        assert _determine_phase_status(agents) == "pending"

    def test_all_completed(self):
        from schemas.workflow import PhaseAgent
        from services.workflow_service import _determine_phase_status

        agents = [
            PhaseAgent(agent_id="a", status="completed"),
            PhaseAgent(agent_id="b", status="completed"),
        ]
        assert _determine_phase_status(agents) == "completed"

    def test_any_failed(self):
        from schemas.workflow import PhaseAgent
        from services.workflow_service import _determine_phase_status

        agents = [
            PhaseAgent(agent_id="a", status="completed"),
            PhaseAgent(agent_id="b", status="failed"),
        ]
        assert _determine_phase_status(agents) == "failed"

    def test_any_active(self):
        from schemas.workflow import PhaseAgent
        from services.workflow_service import _determine_phase_status

        agents = [
            PhaseAgent(agent_id="a", status="active"),
            PhaseAgent(agent_id="b", status="pending"),
        ]
        assert _determine_phase_status(agents) == "active"
