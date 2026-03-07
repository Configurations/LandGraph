"""Agent Loader — Charge tous les agents depuis config/agents_registry.json."""
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


def _find_registry():
    for b in CPATHS:
        p = os.path.join(os.path.abspath(b), "agents_registry.json")
        if os.path.exists(p):
            return p
    return None


def _create_agent(agent_id, conf):
    """Cree dynamiquement une classe agent depuis la config."""
    attrs = {
        "agent_id": agent_id,
        "agent_name": conf["name"],
        "default_temperature": conf.get("temperature", 0.3),
        "default_max_tokens": conf.get("max_tokens", 32768),
        "prompt_filename": conf.get("prompt", f"{agent_id}.md"),
        "pipeline_steps": conf.get("pipeline_steps", []),
        "use_tools": conf.get("use_tools", False),
    }

    # Creer la classe dynamiquement
    AgentClass = type(f"Agent_{agent_id}", (BaseAgent,), attrs)
    return AgentClass()


def load_agents():
    """Charge tous les agents depuis le registry. Retourne un dict {agent_id: instance}."""
    path = _find_registry()
    if not path:
        logger.error("agents_registry.json not found")
        return {}

    with open(path) as f:
        registry = json.load(f)

    agents = {}
    for agent_id, conf in registry.get("agents", {}).items():
        try:
            agents[agent_id] = _create_agent(agent_id, conf)
            logger.info(f"Loaded agent: {agent_id} ({conf['name']})")
        except Exception as e:
            logger.error(f"Failed to load agent {agent_id}: {e}")

    logger.info(f"Total agents loaded: {len(agents)}")
    return agents


# Singleton — charge une seule fois
_agents = None


def get_agents():
    global _agents
    if _agents is None:
        _agents = load_agents()
    return _agents


def get_agent(agent_id):
    agents = get_agents()
    return agents.get(agent_id)
