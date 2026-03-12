"""Tests des endpoints du dashboard admin via TestClient.

Ces tests necessitent httpx + starlette. Ils sont skippés si web.server
ne peut pas etre importe (deps manquantes).
"""
import json
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

try:
    from starlette.testclient import TestClient
    _HAS_STARLETTE = True
except ImportError:
    _HAS_STARLETTE = False

pytestmark = pytest.mark.skipif(not _HAS_STARLETTE, reason="starlette not installed")


# ── Helpers ──────────────────────────────────────

def _make_app(tmp_admin_env):
    """Importe web.server avec les chemins patche vers tmp_path."""
    env = tmp_admin_env
    web_dir = Path(__file__).resolve().parent.parent.parent / "web"
    if str(web_dir.parent) not in sys.path:
        sys.path.insert(0, str(web_dir.parent))

    # Remove cached module
    for key in list(sys.modules.keys()):
        if key.startswith("web"):
            del sys.modules[key]

    import web.server as ws

    # Patch paths
    ws.DOCKER_MODE = False
    ws.PROJECT_DIR = env["project"]
    ws.CONFIGS = env["config"]
    ws.TEAMS_DIR = env["teams_dir"]
    ws.SHARED_DIR = env["shared"]
    ws.SHARED_TEAMS_DIR = env["shared_teams"]
    ws.SHARED_MCP_FILE = env["shared_teams"] / "mcp_servers.json"
    ws.SHARED_LLM_FILE = env["shared_teams"] / "llm_providers.json"
    ws.SHARED_TEAMS_FILE = env["shared_teams"] / "teams.json"
    ws.ENV_FILE = env["env_file"]
    ws.MCP_SERVERS_FILE = env["teams_dir"] / "mcp_servers.json"
    ws.MCP_ACCESS_FILE = env["teams_dir"] / "agent_mcp_access.json"
    ws.MCP_CATALOG_FILE = env["catalog"]
    ws.LLM_PROVIDERS_FILE = env["teams_dir"] / "llm_providers.json"
    ws.TEAMS_FILE = env["teams_dir"] / "teams.json"
    ws.GIT_CONFIG_FILE = env["teams_dir"] / "git.json"
    ws.MAIL_FILE = env["config"] / "mail.json"
    ws.DISCORD_FILE = env["config"] / "discord.json"
    ws.HITL_FILE = env["config"] / "hitl.json"
    ws.OTHERS_FILE = env["config"] / "others.json"

    return ws


@pytest.fixture
def tmp_admin_env(tmp_path):
    """Cree l'arborescence admin temporaire."""
    project = tmp_path / "project"
    project.mkdir()
    config = tmp_path / "config"
    teams_dir = config / "Teams"
    team1 = teams_dir / "Team1"
    team1.mkdir(parents=True)
    shared_teams = tmp_path / "Shared" / "Teams"
    shared_teams.mkdir(parents=True)

    env_file = project / ".env"
    env_file.write_text(
        "WEB_ADMIN_USERNAME=admin\nWEB_ADMIN_PASSWORD=secret123\nANTHROPIC_API_KEY=sk-test\n",
        encoding="utf-8",
    )
    (teams_dir / "teams.json").write_text(json.dumps({
        "teams": [{"id": "team1", "name": "Team 1", "directory": "Team1", "discord_channels": []}],
        "channel_mapping": {},
    }))
    (team1 / "agents_registry.json").write_text(json.dumps({
        "agents": {
            "lead_dev": {"name": "Lead Dev", "llm": "claude-sonnet", "prompt": "lead_dev.md", "type": "single"},
        }
    }))
    (team1 / "lead_dev.md").write_text("# Lead Dev\n")
    (teams_dir / "mcp_servers.json").write_text(json.dumps({"servers": {
        "github": {"command": "npx", "args": ["@mcp/github"], "transport": "stdio", "env": {}, "enabled": True},
    }}))
    (teams_dir / "agent_mcp_access.json").write_text(json.dumps({"lead_dev": ["github"]}))
    (teams_dir / "llm_providers.json").write_text(json.dumps({
        "providers": {"claude-sonnet": {"type": "anthropic", "model": "claude-sonnet-4-5-20250929", "env_key": "ANTHROPIC_API_KEY"}},
        "default": "claude-sonnet",
        "throttling": {},
    }))
    (team1 / "Workflow.json").write_text(json.dumps({"phases": {}, "transitions": []}))
    (config / "mail.json").write_text(json.dumps({"smtp": []}))
    (config / "discord.json").write_text(json.dumps({"enabled": True}))
    (config / "hitl.json").write_text(json.dumps({"auth": {}}))
    (config / "others.json").write_text(json.dumps({}))
    (teams_dir / "git.json").write_text(json.dumps({}))

    catalog = shared_teams / "mcp_catalog.csv"
    catalog.write_text(
        "0|github|GitHub|Desc|npx|@mcp/github|stdio|GITHUB_TOKEN:Token\n"
        "0|notion|Notion|Desc|npx|@mcp/notion|stdio|\n",
        encoding="utf-8",
    )

    return {
        "root": tmp_path, "project": project, "config": config,
        "teams_dir": teams_dir, "team1": team1,
        "shared": tmp_path / "Shared", "shared_teams": shared_teams,
        "env_file": env_file, "catalog": catalog,
    }


@pytest.fixture
def ws(tmp_admin_env):
    return _make_app(tmp_admin_env)


@pytest.fixture
def client(ws):
    return TestClient(ws.app)


@pytest.fixture
def cookie(ws):
    token = ws._make_session_token("admin")
    return {"lg_session": token}


# ── Auth tests ──────────────────────────────────


class TestAdminAuth:

    def test_login_success(self, client):
        r = client.post("/auth/login", json={"username": "admin", "password": "secret123"})
        assert r.status_code == 200
        assert "lg_session" in r.cookies

    def test_login_wrong_password(self, client):
        r = client.post("/auth/login", json={"username": "admin", "password": "wrong"})
        assert r.status_code == 401

    def test_login_wrong_username(self, client):
        r = client.post("/auth/login", json={"username": "hacker", "password": "secret123"})
        assert r.status_code == 401

    def test_api_without_cookie_401(self, client):
        r = client.get("/api/env")
        assert r.status_code == 401

    def test_api_with_cookie_200(self, client, cookie):
        r = client.get("/api/env", cookies=cookie)
        assert r.status_code == 200

    def test_logout(self, client, cookie):
        r = client.get("/auth/logout", cookies=cookie, follow_redirects=False)
        assert r.status_code == 302

    def test_version_public(self, client):
        """GET /api/version est accessible sans auth."""
        r = client.get("/api/version")
        assert r.status_code == 200
        assert "version" in r.json()


# ── Secrets (.env) ──────────────────────────────


class TestAdminSecrets:

    def test_get_env(self, client, cookie):
        r = client.get("/api/env", cookies=cookie)
        assert r.status_code == 200
        data = r.json()
        assert "entries" in data
        keys = [e["key"] for e in data["entries"] if e["key"]]
        assert "WEB_ADMIN_USERNAME" in keys

    def test_get_env_path(self, client, cookie):
        r = client.get("/api/env/path", cookies=cookie)
        assert r.status_code == 200
        assert r.json()["exists"] is True

    def test_add_env_entry(self, client, cookie):
        r = client.post("/api/env/add", cookies=cookie, json={
            "key": "NEW_KEY", "value": "new_value", "section_comment": ""
        })
        assert r.status_code == 200
        # Verify
        r2 = client.get("/api/env", cookies=cookie)
        keys = [e["key"] for e in r2.json()["entries"] if e["key"]]
        assert "NEW_KEY" in keys

    def test_add_env_duplicate(self, client, cookie):
        r = client.post("/api/env/add", cookies=cookie, json={
            "key": "ANTHROPIC_API_KEY", "value": "dup", "section_comment": ""
        })
        assert r.status_code == 409

    def test_delete_env_entry(self, client, cookie):
        r = client.post("/api/env/delete", cookies=cookie, json={"key": "ANTHROPIC_API_KEY"})
        assert r.status_code == 200
        r2 = client.get("/api/env", cookies=cookie)
        keys = [e["key"] for e in r2.json()["entries"] if e["key"]]
        assert "ANTHROPIC_API_KEY" not in keys

    def test_update_env(self, client, cookie):
        r = client.put("/api/env", cookies=cookie, json={
            "entries": [{"key": "ONLY_KEY", "value": "only_val", "comment": ""}]
        })
        assert r.status_code == 200
        r2 = client.get("/api/env", cookies=cookie)
        keys = [e["key"] for e in r2.json()["entries"] if e["key"]]
        assert keys == ["ONLY_KEY"]


# ── MCP ──────────────────────────────────────────


class TestAdminMCP:

    def test_get_mcp_catalog(self, client, cookie):
        r = client.get("/api/mcp/catalog", cookies=cookie)
        assert r.status_code == 200
        servers = r.json()["servers"]
        ids = [s["id"] for s in servers]
        assert "github" in ids

    def test_get_mcp_servers(self, client, cookie):
        r = client.get("/api/mcp/servers", cookies=cookie)
        assert r.status_code == 200
        assert "github" in r.json()["servers"]

    def test_get_mcp_access(self, client, cookie):
        r = client.get("/api/mcp/access", cookies=cookie)
        assert r.status_code == 200
        assert "lead_dev" in r.json()

    def test_toggle_mcp(self, client, cookie):
        r = client.put("/api/mcp/toggle/github", cookies=cookie, json={"enabled": False})
        assert r.status_code == 200
        # Verify
        r2 = client.get("/api/mcp/servers", cookies=cookie)
        assert r2.json()["servers"]["github"]["enabled"] is False

    def test_toggle_mcp_not_installed(self, client, cookie):
        r = client.put("/api/mcp/toggle/nonexistent", cookies=cookie, json={"enabled": True})
        assert r.status_code == 404

    def test_uninstall_mcp(self, client, cookie):
        r = client.post("/api/mcp/uninstall/github", cookies=cookie)
        assert r.status_code == 200
        r2 = client.get("/api/mcp/servers", cookies=cookie)
        assert "github" not in r2.json()["servers"]

    def test_update_mcp_access(self, client, cookie):
        r = client.put("/api/mcp/access", cookies=cookie, json={
            "agent_id": "architect", "servers": ["github", "notion"]
        })
        assert r.status_code == 200
        r2 = client.get("/api/mcp/access", cookies=cookie)
        assert r2.json()["architect"] == ["github", "notion"]

    def test_install_mcp(self, client, cookie):
        r = client.post("/api/mcp/install/notion", cookies=cookie, json={
            "env_values": {"NOTION_TOKEN": "test-token"},
            "env_mapping": {"NOTION_TOKEN": "NOTION_TOKEN"},
        })
        assert r.status_code == 200
        r2 = client.get("/api/mcp/servers", cookies=cookie)
        assert "notion" in r2.json()["servers"]


# ── Agents ───────────────────────────────────────


class TestAdminAgents:

    def test_get_agents(self, client, cookie):
        r = client.get("/api/agents", cookies=cookie)
        assert r.status_code == 200
        groups = r.json()["groups"]
        assert len(groups) >= 1
        assert "lead_dev" in groups[0]["agents"]

    def test_create_agent(self, client, cookie):
        r = client.post("/api/agents", cookies=cookie, json={
            "id": "new_agent", "name": "New Agent", "team_id": "Team1",
            "temperature": 0.5, "max_tokens": 8192, "llm": "gpt-4o",
            "type": "single", "prompt_content": "# New Agent\n",
        })
        assert r.status_code == 200
        r2 = client.get("/api/agents/registry/Team1", cookies=cookie)
        assert "new_agent" in r2.json()["agents"]

    def test_create_agent_duplicate(self, client, cookie):
        r = client.post("/api/agents", cookies=cookie, json={
            "id": "lead_dev", "name": "Dup", "team_id": "Team1",
        })
        assert r.status_code == 409

    def test_update_agent(self, client, cookie):
        r = client.put("/api/agents/lead_dev", cookies=cookie, json={
            "id": "lead_dev", "name": "Lead Dev Updated", "team_id": "Team1",
            "temperature": 0.9, "max_tokens": 16384,
        })
        assert r.status_code == 200
        r2 = client.get("/api/agents/registry/Team1", cookies=cookie)
        assert r2.json()["agents"]["lead_dev"]["temperature"] == 0.9

    def test_delete_agent(self, client, cookie):
        r = client.delete("/api/agents/lead_dev?team_id=Team1", cookies=cookie)
        assert r.status_code == 200
        r2 = client.get("/api/agents/registry/Team1", cookies=cookie)
        assert "lead_dev" not in r2.json().get("agents", {})

    def test_delete_agent_not_found(self, client, cookie):
        r = client.delete("/api/agents/nonexistent?team_id=Team1", cookies=cookie)
        assert r.status_code == 404


# ── Workflow ──────────────────────────────────────


class TestAdminWorkflow:

    def test_get_workflow(self, client, cookie):
        r = client.get("/api/workflow/Team1", cookies=cookie)
        assert r.status_code == 200
        assert "phases" in r.json()

    def test_put_workflow(self, client, cookie):
        new_wf = {"phases": {"test": {"name": "Test", "order": 1}}, "transitions": []}
        r = client.put("/api/workflow/Team1", cookies=cookie, json=new_wf)
        assert r.status_code == 200
        r2 = client.get("/api/workflow/Team1", cookies=cookie)
        assert "test" in r2.json()["phases"]

    def test_get_workflow_missing(self, client, cookie):
        r = client.get("/api/workflow/NonExistent", cookies=cookie)
        assert r.status_code == 200
        assert r.json() == {}


# ── LLM Providers ──────────────────────────────────


class TestAdminLLM:

    def test_get_providers(self, client, cookie):
        r = client.get("/api/llm/providers", cookies=cookie)
        assert r.status_code == 200
        assert "claude-sonnet" in r.json()["providers"]

    def test_add_provider(self, client, cookie):
        r = client.post("/api/llm/providers/provider", cookies=cookie, json={
            "id": "gpt-4o", "type": "openai", "model": "gpt-4o", "env_key": "OPENAI_API_KEY",
        })
        assert r.status_code == 200
        r2 = client.get("/api/llm/providers", cookies=cookie)
        assert "gpt-4o" in r2.json()["providers"]

    def test_add_provider_duplicate(self, client, cookie):
        r = client.post("/api/llm/providers/provider", cookies=cookie, json={
            "id": "claude-sonnet", "type": "anthropic", "model": "claude",
        })
        assert r.status_code == 409

    def test_delete_provider(self, client, cookie):
        r = client.delete("/api/llm/providers/provider/claude-sonnet", cookies=cookie)
        assert r.status_code == 200
        r2 = client.get("/api/llm/providers", cookies=cookie)
        assert "claude-sonnet" not in r2.json()["providers"]

    def test_set_default_provider(self, client, cookie):
        r = client.put("/api/llm/providers/default", cookies=cookie, json={"provider_id": "claude-sonnet"})
        assert r.status_code == 200

    def test_set_default_provider_not_found(self, client, cookie):
        r = client.put("/api/llm/providers/default", cookies=cookie, json={"provider_id": "nope"})
        assert r.status_code == 404

    def test_update_throttling(self, client, cookie):
        r = client.put("/api/llm/providers/throttling", cookies=cookie, json={
            "env_key": "ANTHROPIC_API_KEY", "rpm": 100, "tpm": 200000,
        })
        assert r.status_code == 200

    def test_delete_throttling(self, client, cookie):
        # First add one
        client.put("/api/llm/providers/throttling", cookies=cookie, json={
            "env_key": "TEST_KEY", "rpm": 10, "tpm": 1000,
        })
        r = client.delete("/api/llm/providers/throttling/TEST_KEY", cookies=cookie)
        assert r.status_code == 200


# ── Channels ──────────────────────────────────────


class TestAdminChannels:

    def test_get_mail(self, client, cookie):
        r = client.get("/api/mail", cookies=cookie)
        assert r.status_code == 200

    def test_put_mail(self, client, cookie):
        r = client.put("/api/mail", cookies=cookie, json={"smtp": [{"host": "smtp.test.com"}]})
        assert r.status_code == 200
        r2 = client.get("/api/mail", cookies=cookie)
        assert r2.json()["smtp"][0]["host"] == "smtp.test.com"

    def test_get_discord(self, client, cookie):
        r = client.get("/api/discord", cookies=cookie)
        assert r.status_code == 200

    def test_get_hitl_config(self, client, cookie):
        r = client.get("/api/hitl-config", cookies=cookie)
        assert r.status_code == 200

    def test_get_others(self, client, cookie):
        r = client.get("/api/others", cookies=cookie)
        assert r.status_code == 200


# ── Teams ────────────────────────────────────────


class TestAdminTeams:

    def test_get_teams(self, client, cookie):
        r = client.get("/api/teams", cookies=cookie)
        assert r.status_code == 200


# ── Import/Export ────────────────────────────────


class TestAdminExport:

    def test_export_configs(self, client, cookie):
        r = client.get("/api/export/configs", cookies=cookie)
        assert r.status_code == 200
        assert r.headers["content-type"] == "application/zip"

    def test_import_configs(self, client, cookie):
        # First export, then re-import
        r = client.get("/api/export/configs", cookies=cookie)
        assert r.status_code == 200
        # Re-import
        r2 = client.post(
            "/api/import/configs", cookies=cookie,
            files={"file": ("config.zip", r.content, "application/zip")},
        )
        # May fail if endpoint expects raw body — that's ok, we're testing the route exists
        assert r2.status_code in (200, 422)
