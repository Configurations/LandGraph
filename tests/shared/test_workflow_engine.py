"""Tests pour workflow_engine.py — logique pure, mock load_team_json."""
import pytest
from unittest.mock import patch
from tests.conftest import SAMPLE_WORKFLOW


SAMPLE_REGISTRY = {
    "agents": {
        "lead_dev": {
            "name": "Lead Dev",
            "delegates_to": ["dev_frontend_web", "dev_backend_api"]
        },
        "requirements_analyst": {"name": "Analyste"},
        "legal_advisor": {"name": "Legal"},
        "Architect": {"name": "Architect"},
        "ux_designer": {"name": "UX Designer"},
        "qa_engineer": {"name": "QA"},
        "dev_frontend_web": {"name": "Frontend Dev"},
        "dev_backend_api": {"name": "Backend Dev"},
    }
}


def _mock_load(team_id, filename):
    if "workflow" in filename.lower():
        return SAMPLE_WORKFLOW
    if "agents_registry" in filename.lower():
        return SAMPLE_REGISTRY
    return {}


@pytest.fixture(autouse=True)
def _patch_loader():
    with patch("Agents.Shared.workflow_engine.load_team_json", side_effect=_mock_load):
        from agents.shared.workflow_engine import _workflows
        _workflows.clear()
        yield


class TestLoadWorkflow:
    def test_loads_workflow(self):
        from agents.shared.workflow_engine import load_workflow
        wf = load_workflow("team1")
        assert "phases" in wf
        assert "discovery" in wf["phases"]

    def test_caches_result(self):
        from agents.shared.workflow_engine import load_workflow, _workflows
        load_workflow("team1")
        assert "team1" in _workflows


class TestGetPhase:
    def test_existing_phase(self):
        from agents.shared.workflow_engine import get_phase
        phase = get_phase("discovery", "team1")
        assert phase["name"] == "Discovery"

    def test_unknown_phase(self):
        from agents.shared.workflow_engine import get_phase
        assert get_phase("nonexistent", "team1") == {}


class TestGetOrderedGroups:
    def test_single_group(self):
        from agents.shared.workflow_engine import get_ordered_groups
        assert get_ordered_groups("discovery", "team1") == ["A"]

    def test_multiple_groups(self):
        from agents.shared.workflow_engine import get_ordered_groups
        assert get_ordered_groups("build", "team1") == ["A", "B", "C"]

    def test_unknown_phase(self):
        from agents.shared.workflow_engine import get_ordered_groups
        assert get_ordered_groups("unknown", "team1") == []


class TestGetAgentsForGroup:
    def test_group_a_discovery(self):
        from agents.shared.workflow_engine import get_agents_for_group
        agents = get_agents_for_group("discovery", "A", "team1")
        assert "requirements_analyst" in agents
        assert "legal_advisor" in agents

    def test_group_b_build(self):
        from agents.shared.workflow_engine import get_agents_for_group
        agents = get_agents_for_group("build", "B", "team1")
        assert "dev_frontend_web" in agents
        assert "dev_backend_api" in agents
        assert "lead_dev" not in agents

    def test_nonexistent_group(self):
        from agents.shared.workflow_engine import get_agents_for_group
        assert get_agents_for_group("discovery", "Z", "team1") == []


class TestGetRequiredDeliverables:
    def test_filters_required(self):
        from agents.shared.workflow_engine import get_required_deliverables
        delivs = get_required_deliverables("discovery", "team1")
        assert "A:prd" in delivs
        assert "A:legal_audit" not in delivs

    def test_all_required(self):
        from agents.shared.workflow_engine import get_required_deliverables
        delivs = get_required_deliverables("design", "team1")
        assert "A:wireframes" in delivs
        assert "A:adr" in delivs


class TestCheckPhaseComplete:
    def test_all_complete(self):
        from agents.shared.workflow_engine import check_phase_complete
        outputs = {"A:prd": {"status": "complete"}}
        result = check_phase_complete("discovery", outputs, "team1")
        assert result["complete"] is True

    def test_missing_required(self):
        from agents.shared.workflow_engine import check_phase_complete
        result = check_phase_complete("discovery", {}, "team1")
        assert result["complete"] is False
        assert "A:prd" in result["missing_deliverables"]

    def test_optional_missing_ok(self):
        from agents.shared.workflow_engine import check_phase_complete
        outputs = {"A:prd": {"status": "complete"}}
        result = check_phase_complete("discovery", outputs, "team1")
        assert result["complete"] is True

    def test_unknown_phase(self):
        from agents.shared.workflow_engine import check_phase_complete
        result = check_phase_complete("nonexistent", {}, "team1")
        assert result["complete"] is False


class TestCanTransition:
    def _complete_discovery(self):
        return {"A:prd": {"status": "complete"}}

    def test_allowed_when_complete(self):
        from agents.shared.workflow_engine import can_transition
        result = can_transition("discovery", self._complete_discovery(), team_id="team1")
        assert result["allowed"] is True
        assert result["next_phase"] == "design"

    def test_blocked_when_incomplete(self):
        from agents.shared.workflow_engine import can_transition
        result = can_transition("discovery", {}, team_id="team1")
        assert result["allowed"] is False

    def test_human_gate_flag(self):
        from agents.shared.workflow_engine import can_transition
        result = can_transition("discovery", self._complete_discovery(), team_id="team1")
        assert result["needs_human_gate"] is True

    def test_critical_alerts_block(self):
        from agents.shared.workflow_engine import can_transition
        alerts = [{"level": "critical", "resolved": False}]
        result = can_transition("discovery", self._complete_discovery(), legal_alerts=alerts, team_id="team1")
        assert result["allowed"] is False


class TestGetDeliverablesToDispatch:
    def test_dispatches_group_a_first(self):
        from agents.shared.workflow_engine import get_deliverables_to_dispatch
        result = get_deliverables_to_dispatch("build", {}, "team1")
        groups = set(r["parallel_group"] for r in result)
        assert groups == {"A"}

    def test_group_b_after_a_complete(self):
        from agents.shared.workflow_engine import get_deliverables_to_dispatch
        outputs = {"A:tech_lead_plan": {"status": "complete"}}
        result = get_deliverables_to_dispatch("build", outputs, "team1")
        groups = set(r["parallel_group"] for r in result)
        assert groups == {"B"}
        ids = [r["step"] for r in result]
        assert "frontend_code" in ids
        assert "backend_code" in ids

    def test_group_c_after_b_complete(self):
        from agents.shared.workflow_engine import get_deliverables_to_dispatch
        outputs = {
            "A:tech_lead_plan": {"status": "complete"},
            "B:frontend_code": {"status": "complete"},
            "B:backend_code": {"status": "complete"},
        }
        result = get_deliverables_to_dispatch("build", outputs, "team1")
        ids = [r["step"] for r in result]
        assert "test_report" in ids

    def test_blocks_if_prev_group_incomplete(self):
        from agents.shared.workflow_engine import get_deliverables_to_dispatch
        outputs = {"A:tech_lead_plan": {"status": "complete"}, "B:frontend_code": {"status": "complete"}}
        result = get_deliverables_to_dispatch("build", outputs, "team1")
        ids = [r["step"] for r in result]
        assert "test_report" not in ids

    def test_skips_already_complete(self):
        from agents.shared.workflow_engine import get_deliverables_to_dispatch
        outputs = {"A:prd": {"status": "complete"}, "A:legal_audit": {"status": "complete"}}
        result = get_deliverables_to_dispatch("discovery", outputs, "team1")
        assert result == []

    def test_agent_in_multiple_groups(self):
        from agents.shared.workflow_engine import get_deliverables_to_dispatch
        outputs = {"A:tech_lead_plan": {"status": "complete"}}
        result = get_deliverables_to_dispatch("build", outputs, "team1")
        agent_ids = [r["agent_id"] for r in result]
        assert "dev_frontend_web" in agent_ids
        assert "dev_backend_api" in agent_ids

    def test_empty_for_unknown_phase(self):
        from agents.shared.workflow_engine import get_deliverables_to_dispatch
        assert get_deliverables_to_dispatch("nonexistent", {}, "team1") == []


class TestGetAgentsToDispatch:
    def test_derives_from_deliverables(self):
        from agents.shared.workflow_engine import get_agents_to_dispatch
        result = get_agents_to_dispatch("build", {}, "team1")
        ids = [r["agent_id"] for r in result]
        assert "lead_dev" in ids

    def test_unique_agents(self):
        from agents.shared.workflow_engine import get_agents_to_dispatch
        result = get_agents_to_dispatch("discovery", {}, "team1")
        ids = [r["agent_id"] for r in result]
        assert len(ids) == len(set(ids))

    def test_boss_sub_delegation(self):
        """When an agent has a boss (via delegates_to), dispatch boss instead."""
        from agents.shared.workflow_engine import get_agents_to_dispatch
        # Build phase group B has dev_frontend_web and dev_backend_api
        # Both have lead_dev as boss (delegates_to in registry)
        outputs = {"A:tech_lead_plan": {"status": "complete"}}
        result = get_agents_to_dispatch("build", outputs, "team1")
        ids = [r["agent_id"] for r in result]
        # dev_frontend_web and dev_backend_api should be replaced by lead_dev
        assert "dev_frontend_web" not in ids
        assert "dev_backend_api" not in ids
        assert "lead_dev" in ids


class TestGetWorkflowStatus:
    def test_returns_all_phases(self):
        from agents.shared.workflow_engine import get_workflow_status
        status = get_workflow_status("discovery", {}, "team1")
        assert "discovery" in status["phases"]
        assert "build" in status["phases"]

    def test_current_phase_marked(self):
        from agents.shared.workflow_engine import get_workflow_status
        status = get_workflow_status("discovery", {}, "team1")
        assert status["phases"]["discovery"]["current"] is True
        assert status["phases"]["design"]["current"] is False
