"""Fixtures pour les tests du dashboard admin (web/server.py)."""
import json
import os
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

# On doit patcher les variables module-level AVANT l'import de web.server
# car le module fait beaucoup de choses a l'import (load_dotenv, subprocess, etc.)

_WEB_DIR = Path(__file__).resolve().parent.parent.parent / "web"


@pytest.fixture
def tmp_admin_env(tmp_path):
    """Cree une arborescence complete pour le dashboard admin."""
    project = tmp_path / "project"
    project.mkdir()
    config = tmp_path / "config"
    teams_dir = config / "Teams"
    team1 = teams_dir / "Team1"
    team1.mkdir(parents=True)
    shared = tmp_path / "Shared" / "Teams"
    shared.mkdir(parents=True)

    # .env
    env_file = project / ".env"
    env_file.write_text(
        "# LandGraph\n"
        "WEB_ADMIN_USERNAME=admin\n"
        "WEB_ADMIN_PASSWORD=secret123\n"
        "ANTHROPIC_API_KEY=sk-ant-test\n"
        "DATABASE_URI=postgresql://test:test@localhost/test\n",
        encoding="utf-8",
    )

    # teams.json
    (teams_dir / "teams.json").write_text(json.dumps({
        "teams": [
            {"id": "team1", "name": "Team 1", "directory": "Team1", "discord_channels": ["111"]},
        ],
        "channel_mapping": {"111": "team1"},
    }))

    # agents_registry.json
    (team1 / "agents_registry.json").write_text(json.dumps({
        "agents": {
            "orchestrator": {"name": "Orchestrateur", "llm": "claude-sonnet", "prompt": "orchestrator.md", "type": "orchestrator"},
            "lead_dev": {"name": "Lead Dev", "llm": "claude-sonnet", "prompt": "lead_dev.md", "type": "single"},
        }
    }))

    # prompts
    (team1 / "orchestrator.md").write_text("# Orchestrateur\n")
    (team1 / "lead_dev.md").write_text("# Lead Dev\n")

    # mcp_servers.json
    (teams_dir / "mcp_servers.json").write_text(json.dumps({"servers": {
        "github": {"command": "npx", "args": ["@mcp/github"], "transport": "stdio", "env": {}, "enabled": True},
    }}))

    # agent_mcp_access.json
    (teams_dir / "agent_mcp_access.json").write_text(json.dumps({"lead_dev": ["github"]}))

    # llm_providers.json
    (teams_dir / "llm_providers.json").write_text(json.dumps({
        "providers": {
            "claude-sonnet": {"type": "anthropic", "model": "claude-sonnet-4-5-20250929", "env_key": "ANTHROPIC_API_KEY"},
        },
        "default": "claude-sonnet",
        "throttling": {"ANTHROPIC_API_KEY": {"rpm": 50, "tpm": 100000}},
    }))

    # Workflow.json
    (team1 / "Workflow.json").write_text(json.dumps({"phases": {}, "transitions": []}))

    # Channel configs
    (config / "mail.json").write_text(json.dumps({"smtp": [], "imap": []}))
    (config / "discord.json").write_text(json.dumps({"enabled": True}))
    (config / "hitl.json").write_text(json.dumps({"auth": {"jwt_expire_hours": 24}}))
    (config / "others.json").write_text(json.dumps({"password_reset": {}}))

    # MCP catalog
    catalog = shared / "mcp_catalog.csv"
    catalog.write_text(
        "# deprecated|id|label|description|command|args|transport|env_vars\n"
        "0|github|GitHub|GitHub MCP|npx|@mcp/github|stdio|GITHUB_TOKEN:Token GitHub\n"
        "0|notion|Notion|Notion MCP|npx|@mcp/notion|stdio|NOTION_TOKEN:Token Notion\n"
        "1|old-srv|Old|Deprecated|npx|@mcp/old|stdio|\n",
        encoding="utf-8",
    )

    # git.json (empty)
    (teams_dir / "git.json").write_text(json.dumps({}))

    return {
        "root": tmp_path,
        "project": project,
        "config": config,
        "teams_dir": teams_dir,
        "team1": team1,
        "shared": tmp_path / "Shared",
        "shared_teams": shared,
        "env_file": env_file,
        "catalog": catalog,
    }


@pytest.fixture
def admin_app(tmp_admin_env):
    """Import web.server with patched paths, return the FastAPI app."""
    env = tmp_admin_env

    # Patch module-level constants BEFORE import
    # We need to patch at the module source since it reads them on import
    patches = {
        "DOCKER_MODE": False,
        "PROJECT_DIR": env["project"],
        "CONFIGS": env["config"],
        "TEAMS_DIR": env["teams_dir"],
        "SHARED_DIR": env["shared"],
        "SHARED_TEAMS_DIR": env["shared_teams"],
        "SHARED_MCP_FILE": env["shared_teams"] / "mcp_servers.json",
        "SHARED_LLM_FILE": env["shared_teams"] / "llm_providers.json",
        "SHARED_TEAMS_FILE": env["shared_teams"] / "teams.json",
        "ENV_FILE": env["env_file"],
        "MCP_SERVERS_FILE": env["teams_dir"] / "mcp_servers.json",
        "MCP_ACCESS_FILE": env["teams_dir"] / "agent_mcp_access.json",
        "MCP_CATALOG_FILE": env["catalog"],
        "LLM_PROVIDERS_FILE": env["teams_dir"] / "llm_providers.json",
        "TEAMS_FILE": env["teams_dir"] / "teams.json",
        "GIT_CONFIG_FILE": env["teams_dir"] / "git.json",
        "MAIL_FILE": env["config"] / "mail.json",
        "DISCORD_FILE": env["config"] / "discord.json",
        "HITL_FILE": env["config"] / "hitl.json",
        "OTHERS_FILE": env["config"] / "others.json",
    }

    # Import the module
    web_server_path = str(_WEB_DIR.parent)
    if web_server_path not in sys.path:
        sys.path.insert(0, web_server_path)

    # Remove cached module if any
    for key in list(sys.modules.keys()):
        if key.startswith("web"):
            del sys.modules[key]

    import web.server as ws

    # Apply patches
    for attr, value in patches.items():
        setattr(ws, attr, value)

    return ws


@pytest.fixture
def admin_client(admin_app):
    """Return a test client for the admin FastAPI app."""
    from starlette.testclient import TestClient
    return TestClient(admin_app.app)


@pytest.fixture
def auth_cookie(admin_app):
    """Return a valid session cookie dict."""
    token = admin_app._make_session_token("admin")
    return {"lg_session": token}
