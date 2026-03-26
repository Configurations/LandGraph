"""Agent Loader — Multi-equipes. Charge les agents via team_resolver."""
import json
import logging
import os
import re

from agents.shared.base_agent import BaseAgent
from agents.shared.team_resolver import (
    load_team_json, find_team_file, get_team_for_channel,
    get_all_team_ids, get_teams_config,
)

logger = logging.getLogger(__name__)

VALID_ID = re.compile(r'^[a-z0-9][a-z0-9_-]*$')


def _validate_id(team_id: str) -> bool:
    return bool(VALID_ID.match(team_id))


def _create_agent(agent_id, conf, has_mcp, team_id="default"):
    use_tools = conf.get("use_tools", has_mcp)
    attrs = {
        "agent_id": agent_id,
        "agent_name": conf.get("name", agent_id),
        "default_llm": conf.get("llm", ""),
        "default_model": conf.get("model", "claude-sonnet-4-5-20250929"),
        "default_temperature": conf.get("temperature", 0.3),
        "default_max_tokens": conf.get("max_tokens", 32768),
        "prompt_filename": conf.get("prompt", f"{agent_id}.md"),
        "steps": conf.get("steps", []),
        "use_tools": use_tools,
        "requires_approval": conf.get("requires_approval", False),
        "team_id": team_id,
    }
    AgentClass = type(f"Agent_{agent_id}", (BaseAgent,), attrs)
    return AgentClass()


def load_agents_for_team(team_id="default"):
    """Charge les agents d'une equipe via team_resolver."""
    # Valider l'ID
    if not _validate_id(team_id):
        logger.error(f"Team ID invalide: '{team_id}'")
        return {}

    registry = load_team_json(team_id, "agents_registry.json")
    mcp_access = load_team_json(team_id, "agent_mcp_access.json")

    if not registry:
        logger.error(f"Registry not found for team {team_id}")
        return {}

    agents = {}
    for agent_id, conf in registry.get("agents", {}).items():
        try:
            # Skip orchestrator type — il n'est pas un BaseAgent
            if conf.get("type") == "orchestrator":
                continue
            has_mcp = len(mcp_access.get(agent_id, [])) > 0
            agents[agent_id] = _create_agent(agent_id, conf, has_mcp, team_id)
            tools_info = "tools=True" if agents[agent_id].use_tools else "tools=False"
            logger.info(f"[{team_id}] Loaded: {agent_id} ({conf['name']}) [{tools_info}]")
        except Exception as e:
            logger.error(f"[{team_id}] Failed: {agent_id}: {e}")

    logger.info(f"[{team_id}] {len(agents)} agents loaded")
    return agents


# ── Cache par equipe ─────────────────────────
_teams_agents = {}


def get_agents(team_id: str = "default"):
    if team_id not in _teams_agents:
        _teams_agents[team_id] = load_agents_for_team(team_id)
    return _teams_agents[team_id]


def reload_agents(team_id: str = None):
    """Clear agent cache. If team_id is None, clear all."""
    if team_id:
        _teams_agents.pop(team_id, None)
    else:
        _teams_agents.clear()
    logger.info(f"Agent cache cleared: {team_id or 'all'}")


def get_agent(agent_id: str, team_id: str = "default"):
    agents = get_agents(team_id)
    return agents.get(agent_id)


def get_step_instruction(agent_id: str, step_key: str, team_id: str = "default") -> str:
    """Return the instruction for a specific step from the registry."""
    registry = load_team_json(team_id, "agents_registry.json")
    if not registry:
        return ""
    agent_conf = registry.get("agents", {}).get(agent_id, {})
    for step in agent_conf.get("steps", []):
        if step.get("output_key") == step_key:
            return step.get("instruction", "")
    return ""


def load_agent_supplementary_prompts(agent_id: str) -> str:
    """Load assign + unassign prompts from Shared/Agents/{agent_id}/.
    Returns concatenated text, empty string if files not found."""
    parts = []
    for base in ['/app/shared_agents', '/app/Shared/Agents', 'Shared/Agents']:
        agent_dir = os.path.join(base, agent_id)
        if not os.path.isdir(agent_dir):
            continue
        for suffix in ['_assign.md', '_unassign.md']:
            path = os.path.join(agent_dir, f"{agent_id}{suffix}")
            if os.path.isfile(path):
                try:
                    parts.append(open(path, encoding="utf-8").read())
                except Exception:
                    pass
        if parts:
            break
    return "\n\n".join(parts)
