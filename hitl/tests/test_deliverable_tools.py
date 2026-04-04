"""Tests for Agents/Shared/deliverable_tools.py.

Note: the production code runs on Linux (Docker).  On Windows, os.path.join
treats segments like '42:sprint1' as drive letters and discards prior parts.
We patch os.path.join inside the module with posixpath.join for _build_path
tests so the assertions work cross-platform.
"""

from __future__ import annotations

import os
import posixpath
import sys
import types
from unittest.mock import patch

import pytest

# ── Mock langchain_core before importing the module ───────────

_fake_lc = types.ModuleType("langchain_core")
_fake_lc_tools = types.ModuleType("langchain_core.tools")


def _identity_tool(fn):
    """Fake @tool decorator that wraps the function with .invoke()."""
    class _FakeTool:
        def __init__(self, f):
            self._fn = f
            self.__name__ = f.__name__
            self.__doc__ = f.__doc__
        def invoke(self, args: dict) -> str:
            return self._fn(**args)
    return _FakeTool(fn)


_fake_lc_tools.tool = _identity_tool
_fake_lc.tools = _fake_lc_tools
sys.modules.setdefault("langchain_core", _fake_lc)
sys.modules.setdefault("langchain_core.tools", _fake_lc_tools)

# Now safe to import
for _candidate in [
    "/app/agents/shared",
    os.path.join(os.path.dirname(__file__), '..', '..', 'Agents', 'Shared'),
    os.path.join(os.path.dirname(__file__), '..', '..', 'agents', 'shared'),
]:
    if os.path.isdir(_candidate):
        sys.path.insert(0, _candidate)
        break
import deliverable_tools
from deliverable_tools import set_deliverable_context, _build_path


# ── _build_path ────────────────────────────────────────────────


class TestBuildPath:
    """Tests for _build_path helper.

    We patch os.path.join → posixpath.join inside the module so that
    Windows does not misinterpret colons as drive letters.
    """

    def test_path_with_workflow_and_phase(self, monkeypatch: pytest.MonkeyPatch):
        """With workflow_id + phase_id the full structured path is used."""
        monkeypatch.setenv("AG_FLOW_ROOT", "/data")
        set_deliverable_context({
            "current_phase": "design",
            "workflow_id": "42",
            "workflow_name": "sprint1",
            "phase_id": "7",
            "group_key": "B",
        })
        with patch.object(deliverable_tools.os.path, "join", posixpath.join):
            result = _build_path("my-project", "team1", "architect", "specs")
        assert result == "/data/projects/my-project/team1/42:sprint1/7:design-B/architect/specs.md"

    def test_path_fallback_without_workflow(self, monkeypatch: pytest.MonkeyPatch):
        """Without workflow_id the onboarding fallback is used."""
        monkeypatch.setenv("AG_FLOW_ROOT", "/data")
        set_deliverable_context({
            "current_phase": "discovery",
        })
        with patch.object(deliverable_tools.os.path, "join", posixpath.join):
            result = _build_path("slug", "t1", "lead_dev", "prd")
        assert result == "/data/projects/slug/t1/onboarding/0:discovery/lead_dev/prd.md"

    def test_path_default_group_key(self, monkeypatch: pytest.MonkeyPatch):
        """group_key defaults to 'A' when not provided."""
        monkeypatch.setenv("AG_FLOW_ROOT", "/x")
        set_deliverable_context({
            "workflow_id": "1",
            "workflow_name": "wf",
            "phase_id": "2",
            "current_phase": "build",
        })
        with patch.object(deliverable_tools.os.path, "join", posixpath.join):
            result = _build_path("p", "t", "a", "k")
        assert result == "/x/projects/p/t/1:wf/2:build-A/a/k.md"

    def test_path_missing_workflow_name_uses_default(self, monkeypatch: pytest.MonkeyPatch):
        """When workflow_name is missing, 'workflow' is used as fallback."""
        monkeypatch.setenv("AG_FLOW_ROOT", "/x")
        set_deliverable_context({
            "workflow_id": "5",
            "phase_id": "3",
            "current_phase": "test",
        })
        with patch.object(deliverable_tools.os.path, "join", posixpath.join):
            result = _build_path("p", "t", "a", "k")
        assert "5:workflow" in result
        assert "3:test-A" in result


# ── save_deliverable ──────────────────────────────────────────


# Re-import the tool (it was decorated by our fake @tool)
from deliverable_tools import save_deliverable


class TestSaveDeliverable:
    """Tests for the save_deliverable tool."""

    def test_rejects_empty_content(self):
        """Empty content returns an error message."""
        set_deliverable_context({
            "project_slug": "proj",
            "team_id": "t1",
            "agent_id": "arch",
        })
        result = save_deliverable.invoke({"deliverable_key": "k", "content": "   "})
        assert "Erreur" in result
        assert "vide" in result

    def test_rejects_missing_project_slug(self):
        """Missing project_slug returns an error message."""
        set_deliverable_context({
            "project_slug": "",
            "team_id": "t1",
            "agent_id": "arch",
        })
        result = save_deliverable.invoke({"deliverable_key": "k", "content": "hello"})
        assert "Erreur" in result
        assert "projet" in result

    def test_rejects_missing_agent_id(self):
        """Missing agent_id returns an error message."""
        set_deliverable_context({
            "project_slug": "proj",
            "team_id": "t1",
            "agent_id": "",
        })
        result = save_deliverable.invoke({"deliverable_key": "k", "content": "hello"})
        assert "Erreur" in result
        assert "agent_id" in result

    def test_writes_file_to_disk(self, tmp_path, monkeypatch: pytest.MonkeyPatch):
        """save_deliverable actually creates the file with the right content."""
        monkeypatch.setenv("AG_FLOW_ROOT", str(tmp_path))
        set_deliverable_context({
            "project_slug": "demo",
            "team_id": "team1",
            "agent_id": "analyst",
            "current_phase": "discovery",
        })
        content = "# My deliverable\n\nSome analysis content."

        # On Windows, colons in directory names are illegal.
        # Patch _build_path to produce a Windows-safe path.
        safe_path = os.path.join(
            str(tmp_path), "projects", "demo", "team1",
            "onboarding", "0_discovery", "analyst", "analysis.md",
        )
        with patch("deliverable_tools._build_path", return_value=safe_path):
            result = save_deliverable.invoke({"deliverable_key": "analysis", "content": content})

        assert "Livrable" in result or "sauvegarde" in result.lower()
        assert os.path.exists(safe_path)
        with open(safe_path, encoding="utf-8") as f:
            assert f.read() == content
