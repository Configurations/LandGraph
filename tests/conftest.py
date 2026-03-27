"""Fixtures partagees pour les tests ag.flow."""
import json
import os
import sys
import types
import importlib
import pytest

# ── Gerer le mapping Agents/ -> agents (Windows case-insensitive) ──
# Le dossier s'appelle Agents/ mais le code importe agents.shared.*
# On cree des aliases dans sys.modules pour que les deux formes marchent.
_repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def _setup_agents_alias():
    """Pre-importe Agents/ et cree des aliases agents.* dans sys.modules."""
    if "agents" in sys.modules:
        return

    if _repo_root not in sys.path:
        sys.path.insert(0, _repo_root)

    # Importer les packages principaux
    import Agents
    import Agents.Shared

    sys.modules["agents"] = sys.modules["Agents"]
    sys.modules["agents.shared"] = sys.modules["Agents.Shared"]

    # Auto-decouvrir et aliaser tous les sous-modules de Agents/Shared/
    shared_dir = os.path.join(_repo_root, "Agents", "Shared")
    for fname in os.listdir(shared_dir):
        if fname.endswith(".py") and fname != "__init__.py":
            mod_name = fname[:-3]
            real_key = f"Agents.Shared.{mod_name}"
            alias_key = f"agents.shared.{mod_name}"
            if alias_key not in sys.modules:
                try:
                    importlib.import_module(real_key)
                    sys.modules[alias_key] = sys.modules[real_key]
                except Exception:
                    pass  # Skip modules with missing deps

    # Aliaser les modules de premier niveau (gateway, orchestrator, discord_listener)
    agents_dir = os.path.join(_repo_root, "Agents")
    for fname in os.listdir(agents_dir):
        if fname.endswith(".py") and fname != "__init__.py":
            mod_name = fname[:-3]
            real_key = f"Agents.{mod_name}"
            alias_key = f"agents.{mod_name}"
            if alias_key not in sys.modules:
                try:
                    importlib.import_module(real_key)
                    sys.modules[alias_key] = sys.modules[real_key]
                except Exception:
                    pass

_setup_agents_alias()


# ── Fixture : workflow JSON minimal ──────────────

SAMPLE_WORKFLOW = {
    "phases": {
        "discovery": {
            "name": "Discovery",
            "order": 1,
            "groups": [
                {
                    "id": "A",
                    "deliverables": [
                        {"id": "prd", "Name": "PRD", "agent": "requirements_analyst", "required": True, "type": "specs", "description": "Product Requirements Document", "depends_on": []},
                        {"id": "legal_audit", "Name": "Audit legal", "agent": "legal_advisor", "required": False, "type": "documentation", "description": "Audit legal", "depends_on": []},
                    ],
                },
            ],
            "exit_conditions": {"human_gate": True, "no_critical_alerts": True},
        },
        "design": {
            "name": "Design",
            "order": 2,
            "groups": [
                {
                    "id": "A",
                    "deliverables": [
                        {"id": "wireframes", "Name": "Wireframes", "agent": "ux_designer", "required": True, "type": "design", "description": "Wireframes", "depends_on": []},
                        {"id": "adr", "Name": "ADR", "agent": "architect", "required": True, "type": "specs", "description": "Architecture Decision Records", "depends_on": []},
                    ],
                },
            ],
            "exit_conditions": {"human_gate": False},
        },
        "build": {
            "name": "Build",
            "order": 3,
            "groups": [
                {
                    "id": "A",
                    "deliverables": [
                        {"id": "tech_lead_plan", "Name": "Plan technique", "agent": "lead_dev", "required": True, "type": "specs", "description": "Plan technique du lead dev", "depends_on": []},
                    ],
                },
                {
                    "id": "B",
                    "deliverables": [
                        {"id": "frontend_code", "Name": "Code frontend", "agent": "dev_frontend_web", "required": True, "type": "code", "description": "Code frontend", "depends_on": ["A:tech_lead_plan"]},
                        {"id": "backend_code", "Name": "Code backend", "agent": "dev_backend_api", "required": True, "type": "code", "description": "Code backend", "depends_on": ["A:tech_lead_plan"]},
                    ],
                },
                {
                    "id": "C",
                    "deliverables": [
                        {"id": "test_report", "Name": "Rapport QA", "agent": "qa_engineer", "required": True, "type": "documentation", "description": "Rapport de tests", "depends_on": ["B:frontend_code", "B:backend_code"]},
                    ],
                },
            ],
            "exit_conditions": {},
        },
    },
    "transitions": [
        {"from": "discovery", "to": "design"},
        {"from": "design", "to": "build"},
        {"from": "build", "to": "ship"},
    ],
    "rules": {"max_agents_parallel": 3},
}


SAMPLE_TEAMS = {
    "teams": [
        {"id": "team1", "name": "Team 1", "directory": "Team1", "discord_channels": []},
        {"id": "team2", "name": "Team 2", "directory": "Team2", "discord_channels": []},
    ],
    "channel_mapping": {"123456": "team1", "789012": "team2"},
}


SAMPLE_REGISTRY = {
    "agents": {
        "orchestrator": {
            "name": "Orchestrateur",
            "llm": "claude-sonnet",
            "temperature": 0.2,
            "max_tokens": 4096,
            "prompt": "orchestrator.md",
            "type": "orchestrator",
        },
        "requirements_analyst": {
            "name": "Analyste",
            "llm": "claude-sonnet",
            "temperature": 0.3,
            "max_tokens": 32768,
            "prompt": "requirements_analyst.md",
            "type": "manager",
            "steps": ["analyse", "redaction", "validation"],
        },
        "lead_dev": {
            "name": "Lead Dev",
            "llm": "claude-sonnet",
            "temperature": 0.3,
            "max_tokens": 32768,
            "prompt": "lead_dev.md",
            "type": "single",
            "use_tools": True,
            "requires_approval": False,
        },
        "architect": {
            "name": "Architecte",
            "llm": "gpt-4o",
            "temperature": 0.2,
            "max_tokens": 16384,
            "prompt": "architect.md",
            "type": "single",
        },
    },
}


SAMPLE_MCP_ACCESS = {
    "lead_dev": ["github", "notion"],
    "architect": [],
}


SAMPLE_LLM_PROVIDERS = {
    "providers": {
        "claude-sonnet": {
            "type": "anthropic",
            "model": "claude-sonnet-4-5-20250929",
            "description": "Claude Sonnet",
            "env_key": "ANTHROPIC_API_KEY",
        },
        "gpt-4o": {
            "type": "openai",
            "model": "gpt-4o",
            "description": "GPT-4o",
            "env_key": "OPENAI_API_KEY",
        },
        "ollama-llama3": {
            "type": "ollama",
            "model": "llama3",
            "description": "Llama 3 local",
            "base_url": "http://localhost:11434",
        },
    },
    "default": "claude-sonnet",
    "throttling": {
        "ANTHROPIC_API_KEY": {"rpm": 50, "tpm": 100000},
        "OPENAI_API_KEY": {"rpm": 60, "tpm": 150000},
    },
}


def _do_clear_caches():
    """Fonction utilitaire pour vider les caches module-level."""
    # workflow_engine
    try:
        from Agents.Shared import workflow_engine
        workflow_engine._workflows = {}
    except Exception:
        pass
    # rate_limiter
    try:
        from Agents.Shared import rate_limiter
        rate_limiter._throttling_config = None
        rate_limiter._throttles = {}
    except Exception:
        pass
    # llm_provider
    try:
        from Agents.Shared import llm_provider
        llm_provider._providers_config = None
    except Exception:
        pass
    # team_resolver
    try:
        from Agents.Shared import team_resolver
        team_resolver._configs_dir = None
        team_resolver._teams_dir = None
        team_resolver._teams_config = None
    except Exception:
        pass
    # agent_loader
    try:
        from Agents.Shared import agent_loader
        agent_loader._teams_agents = {}
    except Exception:
        pass
    # event_bus singleton
    try:
        from Agents.Shared import event_bus
        event_bus.EventBus._instance = None
    except Exception:
        pass


@pytest.fixture(autouse=True)
def _clear_module_caches():
    """Vide les caches module-level avant et apres chaque test."""
    _do_clear_caches()
    yield
    _do_clear_caches()



@pytest.fixture
def sample_workflow():
    return SAMPLE_WORKFLOW.copy()


@pytest.fixture
def sample_teams():
    return SAMPLE_TEAMS.copy()


@pytest.fixture
def sample_registry():
    return SAMPLE_REGISTRY.copy()


@pytest.fixture
def sample_llm_providers():
    return SAMPLE_LLM_PROVIDERS.copy()


@pytest.fixture
def tmp_config_dir(tmp_path):
    """Cree une arborescence config/ temporaire avec les fixtures."""
    config_dir = tmp_path / "config"
    teams_dir = config_dir / "Teams"
    team1_dir = teams_dir / "Team1"
    team1_dir.mkdir(parents=True)

    (teams_dir / "teams.json").write_text(json.dumps(SAMPLE_TEAMS))
    (teams_dir / "llm_providers.json").write_text(json.dumps(SAMPLE_LLM_PROVIDERS))
    (team1_dir / "agents_registry.json").write_text(json.dumps(SAMPLE_REGISTRY))
    (team1_dir / "agent_mcp_access.json").write_text(json.dumps(SAMPLE_MCP_ACCESS))
    (team1_dir / "Workflow.json").write_text(json.dumps(SAMPLE_WORKFLOW))

    return config_dir
