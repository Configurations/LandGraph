"""Tests pour workflow_engine.py — logique pure, mock load_team_json."""
import pytest
from unittest.mock import patch
from tests.conftest import SAMPLE_WORKFLOW


def _mock_load(team_id, filename):
    if "workflow" in filename.lower():
        return SAMPLE_WORKFLOW
    return {}


@pytest.fixture(autouse=True)
def _patch_loader():
    with patch("Agents.Shared.workflow_engine.load_team_json", side_effect=_mock_load):
        yield


# ── load_workflow ────────────────────────────────

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

    def test_fallback_lowercase(self):
        """Si Workflow.json retourne {}, tente workflow.json."""
        def mock_load(team_id, filename):
            if filename == "Workflow.json":
                return {}
            if filename == "workflow.json":
                return SAMPLE_WORKFLOW
            return {}

        with patch("Agents.Shared.workflow_engine.load_team_json", side_effect=mock_load):
            from agents.shared.workflow_engine import load_workflow, _workflows
            _workflows.clear()
            wf = load_workflow("fallback_team")
            assert "phases" in wf

    def test_missing_returns_empty_default(self):
        def mock_load(t, f):
            return {}

        with patch("Agents.Shared.workflow_engine.load_team_json", side_effect=mock_load):
            from agents.shared.workflow_engine import load_workflow, _workflows
            _workflows.clear()
            wf = load_workflow("missing_team")
            assert wf == {"phases": {}, "transitions": [], "rules": {}}


# ── get_phase ────────────────────────────────────

class TestGetPhase:
    def test_existing_phase(self):
        from agents.shared.workflow_engine import get_phase
        phase = get_phase("discovery", "team1")
        assert phase["name"] == "Discovery"

    def test_unknown_phase(self):
        from agents.shared.workflow_engine import get_phase
        assert get_phase("nonexistent", "team1") == {}


# ── get_phase_agents ─────────────────────────────

class TestGetPhaseAgents:
    def test_returns_agents_dict(self):
        from agents.shared.workflow_engine import get_phase_agents
        agents = get_phase_agents("discovery", "team1")
        assert "requirements_analyst" in agents
        assert "legal_advisor" in agents

    def test_empty_for_unknown_phase(self):
        from agents.shared.workflow_engine import get_phase_agents
        assert get_phase_agents("unknown", "team1") == {}


# ── get_agents_for_group ─────────────────────────

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


# ── get_ordered_groups ───────────────────────────

class TestGetOrderedGroups:
    def test_single_group(self):
        from agents.shared.workflow_engine import get_ordered_groups
        groups = get_ordered_groups("discovery", "team1")
        assert groups == ["A"]

    def test_multiple_groups_sorted(self):
        from agents.shared.workflow_engine import get_ordered_groups
        groups = get_ordered_groups("build", "team1")
        assert groups == ["A", "B", "C"]

    def test_empty_for_unknown_phase(self):
        from agents.shared.workflow_engine import get_ordered_groups
        assert get_ordered_groups("unknown", "team1") == []


# ── get_required_deliverables ────────────────────

class TestGetRequiredDeliverables:
    def test_filters_required(self):
        from agents.shared.workflow_engine import get_required_deliverables
        delivs = get_required_deliverables("discovery", "team1")
        assert "prd" in delivs
        assert "legal_audit" not in delivs

    def test_all_required(self):
        from agents.shared.workflow_engine import get_required_deliverables
        delivs = get_required_deliverables("design", "team1")
        assert "wireframes" in delivs
        assert "adr" in delivs


# ── get_exit_conditions ──────────────────────────

class TestGetExitConditions:
    def test_with_conditions(self):
        from agents.shared.workflow_engine import get_exit_conditions
        conds = get_exit_conditions("discovery", "team1")
        assert conds["human_gate"] is True
        assert conds["no_critical_alerts"] is True

    def test_empty_conditions(self):
        from agents.shared.workflow_engine import get_exit_conditions
        assert get_exit_conditions("build", "team1") == {}


# ── get_next_phase ───────────────────────────────

class TestGetNextPhase:
    def test_discovery_to_design(self):
        from agents.shared.workflow_engine import get_next_phase
        assert get_next_phase("discovery", "team1") == "design"

    def test_design_to_build(self):
        from agents.shared.workflow_engine import get_next_phase
        assert get_next_phase("design", "team1") == "build"

    def test_unknown_phase(self):
        from agents.shared.workflow_engine import get_next_phase
        assert get_next_phase("nonexistent", "team1") == ""


# ── check_phase_complete ─────────────────────────

class TestCheckPhaseComplete:
    def test_all_complete(self):
        from agents.shared.workflow_engine import check_phase_complete
        outputs = {
            "requirements_analyst": {"status": "complete", "deliverables": {"prd": "..."}},
        }
        result = check_phase_complete("discovery", outputs, "team1")
        assert result["complete"] is True
        assert result["missing_agents"] == []

    def test_missing_required_agent(self):
        from agents.shared.workflow_engine import check_phase_complete
        result = check_phase_complete("discovery", {}, "team1")
        assert result["complete"] is False
        assert "requirements_analyst" in result["missing_agents"]

    def test_agent_not_complete_status(self):
        from agents.shared.workflow_engine import check_phase_complete
        outputs = {
            "requirements_analyst": {"status": "in_progress", "deliverables": {"prd": "..."}},
        }
        result = check_phase_complete("discovery", outputs, "team1")
        assert result["complete"] is False
        assert any("requirements_analyst" in i for i in result["issues"])

    def test_missing_required_deliverable(self):
        from agents.shared.workflow_engine import check_phase_complete
        outputs = {
            "requirements_analyst": {"status": "complete", "deliverables": {}},
        }
        result = check_phase_complete("discovery", outputs, "team1")
        assert result["complete"] is False
        assert len(result["missing_deliverables"]) == 1

    def test_optional_agent_missing_ok(self):
        from agents.shared.workflow_engine import check_phase_complete
        outputs = {
            "requirements_analyst": {"status": "complete", "deliverables": {"prd": "..."}},
            # legal_advisor absent but optional
        }
        result = check_phase_complete("discovery", outputs, "team1")
        assert result["complete"] is True

    def test_unknown_phase(self):
        from agents.shared.workflow_engine import check_phase_complete
        result = check_phase_complete("nonexistent", {}, "team1")
        assert result["complete"] is False
        assert any("inconnue" in i for i in result["issues"])


# ── can_transition ───────────────────────────────

class TestCanTransition:
    def _complete_discovery(self):
        return {
            "requirements_analyst": {"status": "complete", "deliverables": {"prd": "..."}},
        }

    def test_allowed_when_complete(self):
        from agents.shared.workflow_engine import can_transition
        result = can_transition("discovery", self._complete_discovery(), team_id="team1")
        assert result["allowed"] is True
        assert result["next_phase"] == "design"

    def test_blocked_when_incomplete(self):
        from agents.shared.workflow_engine import can_transition
        result = can_transition("discovery", {}, team_id="team1")
        assert result["allowed"] is False
        assert "Agents manquants" in result["reason"]

    def test_no_next_phase(self):
        from agents.shared.workflow_engine import can_transition
        result = can_transition("nonexistent", {}, team_id="team1")
        assert result["allowed"] is False
        assert result["next_phase"] == ""

    def test_critical_alerts_block(self):
        from agents.shared.workflow_engine import can_transition
        alerts = [{"level": "critical", "resolved": False}]
        result = can_transition("discovery", self._complete_discovery(), legal_alerts=alerts, team_id="team1")
        assert result["allowed"] is False
        assert "critique" in result["reason"]

    def test_resolved_alerts_ok(self):
        from agents.shared.workflow_engine import can_transition
        alerts = [{"level": "critical", "resolved": True}]
        result = can_transition("discovery", self._complete_discovery(), legal_alerts=alerts, team_id="team1")
        assert result["allowed"] is True

    def test_human_gate_flag(self):
        from agents.shared.workflow_engine import can_transition
        result = can_transition("discovery", self._complete_discovery(), team_id="team1")
        assert result["needs_human_gate"] is True

    def test_no_human_gate(self):
        from agents.shared.workflow_engine import can_transition
        outputs = {
            "ux_designer": {"status": "complete", "deliverables": {"wireframes": "..."}},
            "architect": {"status": "complete", "deliverables": {"adr": "..."}},
        }
        result = can_transition("design", outputs, team_id="team1")
        assert result.get("needs_human_gate", False) is False


# ── get_agents_to_dispatch ───────────────────────

class TestGetAgentsToDispatch:
    def test_group_a_first(self):
        from agents.shared.workflow_engine import get_agents_to_dispatch
        result = get_agents_to_dispatch("discovery", {}, "team1")
        ids = [r["agent_id"] for r in result]
        assert "requirements_analyst" in ids

    def test_skips_complete_agents(self):
        from agents.shared.workflow_engine import get_agents_to_dispatch
        outputs = {"requirements_analyst": {"status": "complete"}}
        result = get_agents_to_dispatch("discovery", outputs, "team1")
        ids = [r["agent_id"] for r in result]
        assert "requirements_analyst" not in ids

    def test_group_b_after_a(self):
        from agents.shared.workflow_engine import get_agents_to_dispatch
        outputs = {"lead_dev": {"status": "complete"}}
        result = get_agents_to_dispatch("build", outputs, "team1")
        # B agents have delegated_by so they should be skipped
        ids = [r["agent_id"] for r in result]
        # dev_frontend_web and dev_backend_api have delegated_by: lead_dev, so not dispatched
        assert "dev_frontend_web" not in ids
        assert "dev_backend_api" not in ids

    def test_skips_delegated_by(self):
        from agents.shared.workflow_engine import get_agents_to_dispatch
        outputs = {"lead_dev": {"status": "complete"}}
        result = get_agents_to_dispatch("build", outputs, "team1")
        ids = [r["agent_id"] for r in result]
        assert "dev_frontend_web" not in ids

    def test_respects_depends_on(self):
        from agents.shared.workflow_engine import get_agents_to_dispatch
        # qa_engineer depends on dev_frontend_web + dev_backend_api
        outputs = {
            "lead_dev": {"status": "complete"},
            "dev_frontend_web": {"status": "complete"},
            # dev_backend_api NOT complete
        }
        result = get_agents_to_dispatch("build", outputs, "team1")
        ids = [r["agent_id"] for r in result]
        assert "qa_engineer" not in ids

    def test_dispatch_qa_when_deps_met(self):
        from agents.shared.workflow_engine import get_agents_to_dispatch
        outputs = {
            "lead_dev": {"status": "complete"},
            "dev_frontend_web": {"status": "complete"},
            "dev_backend_api": {"status": "complete"},
        }
        result = get_agents_to_dispatch("build", outputs, "team1")
        ids = [r["agent_id"] for r in result]
        assert "qa_engineer" in ids

    def test_empty_for_unknown_phase(self):
        from agents.shared.workflow_engine import get_agents_to_dispatch
        assert get_agents_to_dispatch("nonexistent", {}, "team1") == []

    def test_max_parallel_limit(self):
        from agents.shared.workflow_engine import get_agents_to_dispatch
        result = get_agents_to_dispatch("discovery", {}, "team1")
        assert len(result) <= 3  # max_agents_parallel = 3


# ── get_workflow_status ──────────────────────────

class TestGetWorkflowStatus:
    def test_returns_all_phases(self):
        from agents.shared.workflow_engine import get_workflow_status
        status = get_workflow_status("discovery", {}, "team1")
        assert "discovery" in status["phases"]
        assert "design" in status["phases"]
        assert "build" in status["phases"]

    def test_current_phase_marked(self):
        from agents.shared.workflow_engine import get_workflow_status
        status = get_workflow_status("discovery", {}, "team1")
        assert status["phases"]["discovery"]["current"] is True
        assert status["phases"]["design"]["current"] is False

    def test_agent_status_pending(self):
        from agents.shared.workflow_engine import get_workflow_status
        status = get_workflow_status("discovery", {}, "team1")
        agents = status["phases"]["discovery"]["agents"]
        assert agents["requirements_analyst"]["status"] == "pending"

    def test_agent_status_complete(self):
        from agents.shared.workflow_engine import get_workflow_status
        outputs = {"requirements_analyst": {"status": "complete"}}
        status = get_workflow_status("discovery", outputs, "team1")
        agents = status["phases"]["discovery"]["agents"]
        assert agents["requirements_analyst"]["status"] == "complete"
