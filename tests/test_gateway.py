"""Tests pour gateway.py — fonctions pures et endpoints (mocked).

Note: le gateway a beaucoup de deps (psycopg, langgraph, orchestrator).
On teste les fonctions pures et on mock lourdement pour les endpoints.
"""
import sys
import pytest
from unittest.mock import patch, MagicMock, AsyncMock

# gateway importe psycopg, langgraph, orchestrator, etc.
pytestmark = pytest.mark.skipif(
    "Agents.gateway" not in sys.modules,
    reason="gateway not importable (missing psycopg, langgraph, or orchestrator deps)",
)


# ── _load_aliases ────────────────────────────────

class TestLoadAliases:
    def test_fallback_aliases(self):
        with patch("Agents.Shared.team_resolver.find_global_file", return_value=""):
            # Re-import pour declencher _load_aliases avec le mock
            from agents.gateway import _load_aliases
            aliases = _load_aliases()
            assert aliases["analyste"] == "requirements_analyst"
            assert aliases["lead"] == "lead_dev"
            assert aliases["qa"] == "qa_engineer"
            assert aliases["avocat"] == "legal_advisor"

    def test_aliases_from_file(self, tmp_path):
        import json
        p = tmp_path / "discord.json"
        p.write_text(json.dumps({"aliases": {"custom": "my_agent"}}))
        with patch("Agents.Shared.team_resolver.find_global_file", return_value=str(p)):
            from agents.gateway import _load_aliases
            aliases = _load_aliases()
            assert aliases["custom"] == "my_agent"


# ── resolve_agents ───────────────────────────────

class TestResolveAgents:
    def test_default_team(self):
        mock_agents = {"lead_dev": MagicMock(), "architect": MagicMock()}
        with patch("Agents.gateway.get_agents", return_value=mock_agents), \
             patch("Agents.gateway.get_team_for_channel", return_value="default"), \
             patch("Agents.gateway.ALIASES", {"lead": "lead_dev"}):
            from agents.gateway import resolve_agents
            canonical, agent_map, team_id = resolve_agents("")
            assert team_id == "default"
            assert "lead_dev" in canonical

    def test_alias_resolution(self):
        mock_agents = {"lead_dev": MagicMock()}
        with patch("Agents.gateway.get_agents", return_value=mock_agents), \
             patch("Agents.gateway.get_team_for_channel", return_value="team1"), \
             patch("Agents.gateway.ALIASES", {"lead": "lead_dev"}):
            from agents.gateway import resolve_agents
            _, agent_map, _ = resolve_agents("123")
            assert "lead" in agent_map
            assert agent_map["lead"] is mock_agents["lead_dev"]


# ── post_to_channel ──────────────────────────────

class TestPostToChannel:
    @pytest.mark.asyncio
    async def test_empty_noop(self):
        from agents.gateway import post_to_channel
        # Should not raise
        await post_to_channel("", "", "")

    @pytest.mark.asyncio
    async def test_sends_to_channel(self):
        mock_channel = AsyncMock()
        with patch("Agents.gateway.get_default_channel", return_value=mock_channel):
            from agents.gateway import post_to_channel
            await post_to_channel("12345", "hello")
            mock_channel.send.assert_called_once_with("12345", "hello")

    @pytest.mark.asyncio
    async def test_hitl_chat_prefix(self):
        """thread_id hitl-chat-* ecrit en DB au lieu du canal."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value.__enter__ = lambda s: mock_cursor
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)

        with patch("psycopg.connect", return_value=mock_conn), \
             patch.dict("os.environ", {"DATABASE_URI": "postgresql://test"}):
            from agents.gateway import post_to_channel
            await post_to_channel("", "msg", thread_id="hitl-chat-team1-lead_dev")
            mock_cursor.execute.assert_called_once()


# ── Health endpoint (via app) ────────────────────

class TestHealthEndpoint:
    def test_health(self):
        """GET /health devrait retourner 200."""
        from agents.gateway import app
        from fastapi.testclient import TestClient
        client = TestClient(app, raise_server_exceptions=False)
        response = client.get("/health")
        assert response.status_code == 200
