"""Agent Loader — Charge les agents depuis agents_registry.json + auto-detecte use_tools."""
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


def _load_mcp_access():
    """Charge agent_mcp_access.json pour savoir quels agents ont des MCP."""
    path = _find_file("agent_mcp_access.json")
    if not path:
        return {}
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return {}


def _create_agent(agent_id, conf, has_mcp):
    """Cree dynamiquement une classe agent depuis la config."""
    # use_tools = True si explicite dans le registry OU si l'agent a des MCP configures
    use_tools = conf.get("use_tools", has_mcp)

    attrs = {
        "agent_id": agent_id,
        "agent_name": conf["name"],
        "default_temperature": conf.get("temperature", 0.3),
        "default_max_tokens": conf.get("max_tokens", 32768),
        "prompt_filename": conf.get("prompt", f"{agent_id}.md"),
        "pipeline_steps": conf.get("pipeline_steps", []),
        "use_tools": use_tools,
    }

    AgentClass = type(f"Agent_{agent_id}", (BaseAgent,), attrs)
    return AgentClass()


def load_agents():
    """Charge tous les agents depuis le registry. Retourne un dict {agent_id: instance}."""
    path = _find_file("agents_registry.json")
    if not path:
        logger.error("agents_registry.json not found")
        return {}

    with open(path) as f:
        registry = json.load(f)

    # Charger le mapping MCP pour auto-detecter use_tools
    mcp_access = _load_mcp_access()

    agents = {}
    for agent_id, conf in registry.get("agents", {}).items():
        try:
            has_mcp = len(mcp_access.get(agent_id, [])) > 0
            agents[agent_id] = _create_agent(agent_id, conf, has_mcp)
            tools_info = "tools=True" if agents[agent_id].use_tools else "tools=False"
            logger.info(f"Loaded agent: {agent_id} ({conf['name']}) [{tools_info}]")
        except Exception as e:
            logger.error(f"Failed to load agent {agent_id}: {e}")

    logger.info(f"Total agents loaded: {len(agents)}")
    return agents


# Singleton
_agents = None


def get_agents():
    global _agents
    if _agents is None:
        _agents = load_agents()
    return _agents


def get_agent(agent_id):
    agents = get_agents()
    return agents.get(agent_id)
