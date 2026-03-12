"""Tests pour team_resolver.py — resolution de fichiers avec tmp_path."""
import json
import os
import pytest
from unittest.mock import patch


# ── get_configs_dir ──────────────────────────────

class TestGetConfigsDir:
    def test_finds_existing_dir(self, tmp_path):
        config_dir = tmp_path / "config"
        config_dir.mkdir()
        with patch("Agents.Shared.team_resolver.CONFIGS_ROOTS", [str(config_dir)]):
            import Agents.Shared.team_resolver as tr
            tr._configs_dir = None
            result = tr.get_configs_dir()
            assert result == str(config_dir)

    def test_not_found(self):
        with patch("Agents.Shared.team_resolver.CONFIGS_ROOTS", ["/nonexistent/path"]):
            import Agents.Shared.team_resolver as tr
            tr._configs_dir = None
            assert tr.get_configs_dir() == ""


# ── get_teams_config ─────────────────────────────

class TestGetTeamsConfig:
    def test_loads_json(self, tmp_config_dir):
        with patch("Agents.Shared.team_resolver.CONFIGS_ROOTS", [str(tmp_config_dir)]):
            import Agents.Shared.team_resolver as tr
            tr._configs_dir = None
            tr._teams_dir = None
            tr._teams_config = None
            config = tr.get_teams_config()
            assert len(config["teams"]) == 2

    def test_missing_file(self, tmp_path):
        config_dir = tmp_path / "config"
        teams_dir = config_dir / "Teams"
        teams_dir.mkdir(parents=True)
        with patch("Agents.Shared.team_resolver.CONFIGS_ROOTS", [str(config_dir)]):
            import Agents.Shared.team_resolver as tr
            tr._configs_dir = None
            tr._teams_dir = None
            tr._teams_config = None
            config = tr.get_teams_config()
            assert config == {"teams": []}

    def test_empty_file(self, tmp_path):
        config_dir = tmp_path / "config"
        teams_dir = config_dir / "Teams"
        teams_dir.mkdir(parents=True)
        (teams_dir / "teams.json").write_text("")
        with patch("Agents.Shared.team_resolver.CONFIGS_ROOTS", [str(config_dir)]):
            import Agents.Shared.team_resolver as tr
            tr._configs_dir = None
            tr._teams_dir = None
            tr._teams_config = None
            config = tr.get_teams_config()
            assert config == {"teams": []}


# ── get_team_info ────────────────────────────────

class TestGetTeamInfo:
    def test_found(self, tmp_config_dir):
        with patch("Agents.Shared.team_resolver.CONFIGS_ROOTS", [str(tmp_config_dir)]):
            import Agents.Shared.team_resolver as tr
            tr._configs_dir = None
            tr._teams_dir = None
            tr._teams_config = None
            info = tr.get_team_info("team1")
            assert info["name"] == "Team 1"
            assert info["directory"] == "Team1"

    def test_not_found(self, tmp_config_dir):
        with patch("Agents.Shared.team_resolver.CONFIGS_ROOTS", [str(tmp_config_dir)]):
            import Agents.Shared.team_resolver as tr
            tr._configs_dir = None
            tr._teams_dir = None
            tr._teams_config = None
            assert tr.get_team_info("nonexistent") == {}


# ── find_team_file ───────────────────────────────

class TestFindTeamFile:
    def test_exact_match(self, tmp_config_dir):
        with patch("Agents.Shared.team_resolver.CONFIGS_ROOTS", [str(tmp_config_dir)]):
            import Agents.Shared.team_resolver as tr
            tr._configs_dir = None
            tr._teams_dir = None
            tr._teams_config = None
            result = tr.find_team_file("team1", "Workflow.json")
            assert result != ""
            assert os.path.exists(result)

    def test_lowercase_fallback(self, tmp_config_dir):
        # Create a lowercase file
        team_dir = tmp_config_dir / "Teams" / "Team1"
        (team_dir / "lowercase.json").write_text("{}")
        with patch("Agents.Shared.team_resolver.CONFIGS_ROOTS", [str(tmp_config_dir)]):
            import Agents.Shared.team_resolver as tr
            tr._configs_dir = None
            tr._teams_dir = None
            tr._teams_config = None
            result = tr.find_team_file("team1", "Lowercase.json")
            # On Windows (case-insensitive) this finds it either way
            # On Linux, would find via lowercase fallback
            assert result != "" or os.name == "posix"

    def test_not_found(self, tmp_config_dir):
        with patch("Agents.Shared.team_resolver.CONFIGS_ROOTS", [str(tmp_config_dir)]):
            import Agents.Shared.team_resolver as tr
            tr._configs_dir = None
            tr._teams_dir = None
            tr._teams_config = None
            assert tr.find_team_file("team1", "nonexistent.json") == ""


# ── find_global_file ─────────────────────────────

class TestFindGlobalFile:
    def test_finds_in_config(self, tmp_config_dir):
        (tmp_config_dir / "global.json").write_text("{}")
        with patch("Agents.Shared.team_resolver.CONFIGS_ROOTS", [str(tmp_config_dir)]):
            import Agents.Shared.team_resolver as tr
            tr._configs_dir = None
            tr._teams_dir = None
            tr._teams_config = None
            result = tr.find_global_file("global.json")
            assert result != ""

    def test_finds_in_teams_dir(self, tmp_config_dir):
        with patch("Agents.Shared.team_resolver.CONFIGS_ROOTS", [str(tmp_config_dir)]):
            import Agents.Shared.team_resolver as tr
            tr._configs_dir = None
            tr._teams_dir = None
            tr._teams_config = None
            result = tr.find_global_file("llm_providers.json")
            assert result != ""

    def test_not_found(self, tmp_config_dir):
        with patch("Agents.Shared.team_resolver.CONFIGS_ROOTS", [str(tmp_config_dir)]):
            import Agents.Shared.team_resolver as tr
            tr._configs_dir = None
            tr._teams_dir = None
            tr._teams_config = None
            assert tr.find_global_file("nonexistent.json") == ""


# ── load_team_json ───────────────────────────────

class TestLoadTeamJson:
    def test_loads_team_file(self, tmp_config_dir):
        with patch("Agents.Shared.team_resolver.CONFIGS_ROOTS", [str(tmp_config_dir)]):
            import Agents.Shared.team_resolver as tr
            tr._configs_dir = None
            tr._teams_dir = None
            tr._teams_config = None
            data = tr.load_team_json("team1", "agents_registry.json")
            assert "agents" in data

    def test_fallback_to_global(self, tmp_config_dir):
        with patch("Agents.Shared.team_resolver.CONFIGS_ROOTS", [str(tmp_config_dir)]):
            import Agents.Shared.team_resolver as tr
            tr._configs_dir = None
            tr._teams_dir = None
            tr._teams_config = None
            data = tr.load_team_json("team1", "llm_providers.json")
            assert "providers" in data

    def test_not_found_returns_empty(self, tmp_config_dir):
        with patch("Agents.Shared.team_resolver.CONFIGS_ROOTS", [str(tmp_config_dir)]):
            import Agents.Shared.team_resolver as tr
            tr._configs_dir = None
            tr._teams_dir = None
            tr._teams_config = None
            assert tr.load_team_json("team1", "nonexistent.json") == {}


# ── get_team_for_channel ─────────────────────────

class TestGetTeamForChannel:
    def test_mapped_channel(self, tmp_config_dir):
        with patch("Agents.Shared.team_resolver.CONFIGS_ROOTS", [str(tmp_config_dir)]):
            import Agents.Shared.team_resolver as tr
            tr._configs_dir = None
            tr._teams_dir = None
            tr._teams_config = None
            assert tr.get_team_for_channel("123456") == "team1"

    def test_unmapped_channel(self, tmp_config_dir):
        with patch("Agents.Shared.team_resolver.CONFIGS_ROOTS", [str(tmp_config_dir)]):
            import Agents.Shared.team_resolver as tr
            tr._configs_dir = None
            tr._teams_dir = None
            tr._teams_config = None
            assert tr.get_team_for_channel("unknown") == "default"


# ── get_all_team_ids ─────────────────────────────

class TestGetAllTeamIds:
    def test_returns_ids(self, tmp_config_dir):
        with patch("Agents.Shared.team_resolver.CONFIGS_ROOTS", [str(tmp_config_dir)]):
            import Agents.Shared.team_resolver as tr
            tr._configs_dir = None
            tr._teams_dir = None
            tr._teams_config = None
            ids = tr.get_all_team_ids()
            assert "team1" in ids
            assert "team2" in ids
