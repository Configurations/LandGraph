"""Agent Loader — Multi-equipes. Charge les agents depuis teams.json + agents_registry."""
import json
import logging
import os

from agents.shared.base_agent import BaseAgent

logger = logging.getLogger(__name__)

CPATHS = [
    os.path.join(os.path.dirname(__file__), "..", "config"),
    os.path.join(os.path.dirname(__file__), "config"),
    os.path.join("/app", "config"),
]


def _find_file(filename):
    for b in CPATHS:
        p = os.path.join(os.path.abspath(b), filename)
        if os.path.exists(p):
            return p
    return None


def _load_json(filename):
    path = _find_file(filename)
    if not path:
        return {}
    with open(path) as f:
        return json.load(f)


def _load_mcp_access(filename="agent_mcp_access.json"):
    return _load_json(filename)


def _load_teams_config():
    return _load_json("teams.json")


def _create_agent(agent_id, conf, has_mcp):
    use_tools = conf.get("use_tools", has_mcp)

    attrs = {
        "agent_id": agent_id,
        "agent_name": conf["name"],
        "default_llm": conf.get("llm", ""),
        "default_model": conf.get("model", "claude-sonnet-4-5-20250929"),
        "default_temperature": conf.get("temperature", 0.3),
        "default_max_tokens": conf.get("max_tokens", 32768),
        "prompt_filename": conf.get("prompt", f"{agent_id}.md"),
        "pipeline_steps": conf.get("pipeline_steps", []),
        "use_tools": use_tools,
        "requires_approval": conf.get("requires_approval", False),
    }

    AgentClass = type(f"Agent_{agent_id}", (BaseAgent,), attrs)
    return AgentClass()


def load_agents_for_team(team_id="default"):
    """Charge les agents d'une equipe specifique."""
    teams_config = _load_teams_config()
    teams = teams_config.get("teams", {})

    if team_id not in teams:
        team_id = "default"

    team = teams.get(team_id, {})
    registry_file = team.get("agents_registry", "agents_registry.json")
    mcp_file = team.get("mcp_access", "agent_mcp_access.json")

    registry = _load_json(registry_file)
    mcp_access = _load_json(mcp_file)

    if not registry:
        logger.error(f"Registry {registry_file} not found for team {team_id}")
        return {}

    agents = {}
    for agent_id, conf in registry.get("agents", {}).items():
        try:
            has_mcp = len(mcp_access.get(agent_id, [])) > 0
            agents[agent_id] = _create_agent(agent_id, conf, has_mcp)
            tools_info = "tools=True" if agents[agent_id].use_tools else "tools=False"
            logger.info(f"[{team_id}] Loaded: {agent_id} ({conf['name']}) [{tools_info}]")
        except Exception as e:
            logger.error(f"[{team_id}] Failed: {agent_id}: {e}")

    logger.info(f"[{team_id}] {len(agents)} agents loaded")
    return agents


def get_team_for_channel(channel_id: str) -> str:
    """Retourne l'ID de l'equipe pour un channel Discord donne."""
    teams_config = _load_teams_config()
    mapping = teams_config.get("channel_mapping", {})
    return mapping.get(channel_id, "default")


# ── Cache par equipe ─────────────────────────
_teams_agents = {}


def get_agents(team_id: str = "default"):
    """Retourne les agents d'une equipe (cache)."""
    if team_id not in _teams_agents:
        _teams_agents[team_id] = load_agents_for_team(team_id)
    return _teams_agents[team_id]


def get_agent(agent_id: str, team_id: str = "default"):
    """Retourne un agent specifique d'une equipe."""
    agents = get_agents(team_id)
    return agents.get(agent_id)


def get_all_team_ids():
    """Liste toutes les equipes configurees."""
    teams_config = _load_teams_config()
    return list(teams_config.get("teams", {}).keys())
