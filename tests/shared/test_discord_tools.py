"""Tests pour discord_tools.py — fonctions utilitaires texte.

Note: discord_tools.py est fortement couple a discord.py (import top-level).
On ne teste ici que les aspects qui ne necessitent pas de bot Discord.
Si l'import echoue (discord pas installe), on skip le module.
"""
import pytest

discord_tools = pytest.importorskip("agents.shared.discord_tools")


# ── Color constants ──────────────────────────────

class TestConstants:
    def test_channel_review_is_int(self):
        assert isinstance(discord_tools.CHANNEL_REVIEW, int)

    def test_channel_logs_is_int(self):
        assert isinstance(discord_tools.CHANNEL_LOGS, int)

    def test_channel_alerts_is_int(self):
        assert isinstance(discord_tools.CHANNEL_ALERTS, int)
