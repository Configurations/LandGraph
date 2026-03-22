"""Application settings — pydantic-settings based."""

from __future__ import annotations

import json
import os
from functools import lru_cache
from typing import Any, Optional

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """All env-based settings for the HITL console."""

    # Database
    database_uri: str  # Required — set DATABASE_URI env var
    redis_uri: str = ""  # Optional — set REDIS_URI if using Redis
    db_pool_min: int = 2
    db_pool_max: int = 10

    # JWT
    hitl_jwt_secret: str = "change-me"

    # Admin seed
    hitl_admin_email: str = "admin@langgraph.local"
    hitl_admin_password: str = "admin"

    # URLs
    hitl_public_url: str = "http://localhost:8090"
    hitl_internal_url: str = "http://langgraph-hitl:8090"  # Internal Docker network URL
    dispatcher_url: str = "http://langgraph-dispatcher:8070"
    langgraph_api_url: str = ""
    ag_flow_root: str = ""

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"

    def model_post_init(self, __context: Any) -> None:
        """Fallback: HITL_JWT_SECRET ← MCP_SECRET ← 'change-me'."""
        raw = os.getenv(
            "HITL_JWT_SECRET",
            os.getenv("MCP_SECRET", "change-me"),
        )
        object.__setattr__(self, "hitl_jwt_secret", raw)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Singleton settings instance."""
    return Settings()


settings: Settings = get_settings()


# ── Config file helpers ──────────────────────────


_CONFIG_DIR: Optional[str] = None


def _find_config_dir() -> str:
    """Find the config directory containing teams.json."""
    global _CONFIG_DIR
    if _CONFIG_DIR is not None:
        return _CONFIG_DIR
    candidates = [
        "/app/config",
        "config",
        os.path.join(os.path.dirname(__file__), "..", "..", "config"),
    ]
    for candidate in candidates:
        teams_path = os.path.join(candidate, "teams.json")
        if os.path.isdir(candidate) and os.path.isfile(teams_path):
            _CONFIG_DIR = os.path.abspath(candidate)
            return _CONFIG_DIR
    _CONFIG_DIR = "config"
    return _CONFIG_DIR


def load_json_config(filename: str) -> dict[str, Any]:
    """Load a JSON config file from the config directory."""
    path = os.path.join(_find_config_dir(), filename)
    if os.path.isfile(path):
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    return {}


def load_teams() -> list[dict[str, Any]]:
    """Load teams list from teams.json."""
    data = load_json_config("teams.json")
    return data.get("teams", [])
