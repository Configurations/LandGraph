"""Tests pour agent_loader.py — chargement dynamique d'agents."""
import sys
import pytest
from unittest.mock import patch, MagicMock
from tests.conftest import SAMPLE_REGISTRY, SAMPLE_MCP_ACCESS

# agent_loader importe base_agent qui requiert langchain_core
pytestmark = pytest.mark.skipif(
    "Agents.Shared.agent_loader" not in sys.modules,
    reason="agent_loader not importable (missing langchain_core or base_agent deps)",
)


# ── _validate_id ─────────────────────────────────

class TestValidateId:
    def test_valid_ids(self):
        from agents.shared.agent_loader import _validate_id
        assert _validate_id("team1") is True
        assert _validate_id("my-team") is True
        assert _validate_id("team_2") is True
        assert _validate_id("a") is True

    def test_invalid_ids(self):
        from agents.shared.agent_loader import _validate_id
        assert _validate_id("Team1") is False  # uppercase
        assert _validate_id("../hack") is False
        assert _validate_id("") is False
        assert _validate_id("-starts-with-dash") is False
        assert _validate_id("_starts-with-underscore") is False


# ── load_agents_for_team ─────────────────────────

class TestLoadAgentsForTeam:
    @pytest.fixture(autouse=True)
    def _mock_deps(self):
        """Mock BaseAgent pour eviter les imports lourds."""
        # Creer une classe mock qui accepte les attributs dynamiques
        class MockBaseAgent:
            def __init__(self):
                pass

        with patch("Agents.Shared.agent_loader.load_team_json") as mock_load, \
             patch("Agents.Shared.agent_loader.BaseAgent", MockBaseAgent):
            self.mock_load = mock_load
            yield

    def _setup_registry(self):
        def load_side_effect(team_id, filename):
            if "registry" in filename:
                return SAMPLE_REGISTRY
            if "mcp" in filename:
                return SAMPLE_MCP_ACCESS
            return {}
        self.mock_load.side_effect = load_side_effect

    def test_skips_orchestrator(self):
        self._setup_registry()
        from agents.shared.agent_loader import load_agents_for_team
        agents = load_agents_for_team("team1")
        assert "orchestrator" not in agents

    def test_loads_non_orchestrator_agents(self):
        self._setup_registry()
        from agents.shared.agent_loader import load_agents_for_team
        agents = load_agents_for_team("team1")
        assert "requirements_analyst" in agents
        assert "lead_dev" in agents
        assert "architect" in agents

    def test_mcp_detection(self):
        self._setup_registry()
        from agents.shared.agent_loader import load_agents_for_team
        agents = load_agents_for_team("team1")
        # lead_dev has MCP access ["github", "notion"]
        assert agents["lead_dev"].use_tools is True

    def test_no_mcp(self):
        self._setup_registry()
        from agents.shared.agent_loader import load_agents_for_team
        agents = load_agents_for_team("team1")
        # architect has empty MCP access
        # use_tools defaults to has_mcp (False) since not set in registry
        assert agents["architect"].use_tools is False

    def test_invalid_team_id(self):
        from agents.shared.agent_loader import load_agents_for_team
        agents = load_agents_for_team("../Invalid")
        assert agents == {}

    def test_missing_registry(self):
        self.mock_load.return_value = {}
        from agents.shared.agent_loader import load_agents_for_team
        agents = load_agents_for_team("team1")
        assert agents == {}


# ── get_agents / get_agent (caching) ─────────────

class TestGetAgents:
    def test_caches_result(self):
        with patch("Agents.Shared.agent_loader.load_agents_for_team", return_value={"a": "agent"}) as mock:
            from agents.shared.agent_loader import get_agents, _teams_agents
            _teams_agents.clear()
            get_agents("team1")
            get_agents("team1")
            mock.assert_called_once()

    def test_get_agent_by_id(self):
        with patch("Agents.Shared.agent_loader.load_agents_for_team", return_value={"lead_dev": "ld_agent"}):
            from agents.shared.agent_loader import get_agent, _teams_agents
            _teams_agents.clear()
            assert get_agent("lead_dev", "team1") == "ld_agent"

    def test_get_agent_not_found(self):
        with patch("Agents.Shared.agent_loader.load_agents_for_team", return_value={}):
            from agents.shared.agent_loader import get_agent, _teams_agents
            _teams_agents.clear()
            assert get_agent("nonexistent", "team1") is None
