"""Agent routes — list agents for a team with pending question counts."""

from __future__ import annotations

import json
import os

import structlog
from fastapi import APIRouter, Depends, HTTPException

from core.config import _find_config_dir, load_teams
from core.database import fetch_one
from core.security import TokenData, get_current_user
from schemas.chat import AgentResponse
from services.avatar_resolver import resolve_agent_avatar

log = structlog.get_logger(__name__)

router = APIRouter(tags=["agents"])


def _get_team_directory(team_id: str) -> str | None:
    """Resolve the config directory name for a team."""
    teams = load_teams()
    for t in teams:
        if t["id"] == team_id:
            return t.get("directory", "")
    return None


def _load_agents_registry(team_id: str) -> dict:
    """Load agents_registry.json for a team."""
    team_dir = _get_team_directory(team_id)
    if team_dir is None:
        return {}

    config_dir = _find_config_dir()
    path = os.path.join(config_dir, "Teams", team_dir, "agents_registry.json")
    if not os.path.isfile(path):
        # Try without Teams/ prefix
        path = os.path.join(config_dir, team_dir, "agents_registry.json")
    if not os.path.isfile(path):
        return {}

    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError) as exc:
        log.warning("agents_registry_load_error", team_id=team_id, error=str(exc))
        return {}


@router.get("/api/teams/{team_id}/agents", response_model=list[AgentResponse])
async def list_agents(
    team_id: str,
    user: TokenData = Depends(get_current_user),
) -> list[AgentResponse]:
    """List agents for a team with pending question counts."""
    registry = _load_agents_registry(team_id)
    agents_map = registry.get("agents", {})
    if not agents_map:
        raise HTTPException(status_code=404, detail="agents.registry_not_found")

    result: list[AgentResponse] = []
    for agent_id, agent_cfg in agents_map.items():
        # Count pending HITL questions for this agent
        row = await fetch_one(
            """
            SELECT COUNT(*) AS cnt
            FROM project.hitl_requests
            WHERE agent_id = $1 AND team_id = $2 AND status = 'pending'
            """,
            agent_id, team_id,
        )
        pending = row["cnt"] if row else 0

        result.append(AgentResponse(
            id=agent_id,
            name=agent_cfg.get("name", agent_id),
            llm=agent_cfg.get("llm", ""),
            type=agent_cfg.get("type", "single"),
            pending_questions=pending,
            avatar_url=resolve_agent_avatar(team_id, agent_id),
        ))

    return result
