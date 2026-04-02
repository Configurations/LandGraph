"""Resolve avatar URLs for agents from team config + avatar files."""

from __future__ import annotations

import json
import os
import time
from typing import Any

AVATARS_DIR = os.environ.get("AVATARS_DIR", "/app/avatars")
CONFIG_DIR = os.environ.get("CONFIG_DIR", "/app/config")

_cache: dict[str, Any] = {}
_cache_ts: float = 0.0
_CACHE_TTL = 60.0


def _load_config() -> tuple[list[dict], dict[str, dict]]:
    """Load teams.json and agents_registry.json files, with caching."""
    global _cache, _cache_ts
    now = time.monotonic()
    if _cache and (now - _cache_ts) < _CACHE_TTL:
        return _cache["teams"], _cache["registries"]

    teams: list[dict] = []
    registries: dict[str, dict] = {}

    teams_file = os.path.join(CONFIG_DIR, "teams.json")
    if os.path.isfile(teams_file):
        try:
            with open(teams_file, encoding="utf-8") as f:
                data = json.load(f)
            teams = data.get("teams", [])
        except (OSError, json.JSONDecodeError):
            pass

    for team in teams:
        directory = team.get("directory", "")
        if not directory:
            continue
        reg_path = os.path.join(CONFIG_DIR, "Teams", directory, "agents_registry.json")
        if not os.path.isfile(reg_path):
            reg_path = os.path.join(CONFIG_DIR, directory, "agents_registry.json")
        if os.path.isfile(reg_path):
            try:
                with open(reg_path, encoding="utf-8") as f:
                    registries[team["id"]] = json.load(f)
            except (OSError, json.JSONDecodeError):
                pass

    _cache = {"teams": teams, "registries": registries}
    _cache_ts = now
    return teams, registries


def resolve_agent_avatar(team_id: str, agent_id: str) -> str | None:
    """Resolve the avatar URL for an agent.

    Returns /avatars/{theme}/{filename} or None.
    """
    teams, registries = _load_config()

    # Find team's avatar_theme
    team = next((t for t in teams if t["id"] == team_id), None)
    if not team:
        return None
    avatar_theme = team.get("avatar_theme", "")
    if not avatar_theme:
        return None

    # Find agent's avatar field in registry (case-insensitive fallback)
    registry = registries.get(team_id, {})
    agents = registry.get("agents", {})
    agent_cfg = agents.get(agent_id)
    if agent_cfg is None:
        agent_id_lower = agent_id.lower()
        for aid, cfg in agents.items():
            if aid.lower() == agent_id_lower:
                agent_cfg = cfg
                break
    if not agent_cfg:
        return None
    avatar_file = agent_cfg.get("avatar", "")
    if not avatar_file:
        return None

    # Verify file exists on disk
    full_path = os.path.join(AVATARS_DIR, avatar_theme, avatar_file)
    if not os.path.isfile(full_path):
        return None

    return f"/avatars/{avatar_theme}/{avatar_file}"


def invalidate_cache() -> None:
    """Force cache refresh on next call."""
    global _cache_ts
    _cache_ts = 0.0
