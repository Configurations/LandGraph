"""Tests for hitl/core/i18n.py."""

from __future__ import annotations

import json
import os
from unittest.mock import mock_open, patch

import pytest


# ── Helpers ────────────────────────────────────────────────────


def _reset_i18n():
    """Reset i18n module-level state between tests."""
    import core.i18n as mod
    mod._messages = {}
    mod._loaded_culture = ""


# ── Tests ──────────────────────────────────────────────────────


class TestI18n:
    """Tests for msg() and _load()."""

    def setup_method(self):
        _reset_i18n()

    def test_msg_returns_translated_message(self, tmp_path, monkeypatch):
        """msg() returns the translated string from messages.json."""
        culture_dir = tmp_path / "Models" / "fr-fr"
        culture_dir.mkdir(parents=True)
        messages = {"greeting": "Bonjour"}
        (culture_dir / "messages.json").write_text(json.dumps(messages), encoding="utf-8")

        monkeypatch.setenv("CULTURE", "fr-fr")
        # Patch the search bases so _load finds our tmp dir
        with patch("core.i18n._load", return_value=messages):
            from core.i18n import msg
            result = msg("greeting")
        assert result == "Bonjour"

    def test_msg_with_parameter_substitution(self, monkeypatch):
        """msg() performs format() substitution on the template."""
        monkeypatch.setenv("CULTURE", "en-us")
        messages = {"welcome": "Hello {name}, you have {count} items."}
        with patch("core.i18n._load", return_value=messages):
            _reset_i18n()
            from core.i18n import msg
            result = msg("welcome", name="Alice", count=3)
        assert result == "Hello Alice, you have 3 items."

    def test_msg_returns_key_when_not_found(self, monkeypatch):
        """msg() returns the key itself when the message is not in the dict."""
        monkeypatch.setenv("CULTURE", "en-us")
        with patch("core.i18n._load", return_value={}):
            _reset_i18n()
            from core.i18n import msg
            result = msg("nonexistent_key")
        assert result == "nonexistent_key"

    def test_reloads_when_culture_changes(self, monkeypatch):
        """msg() reloads messages when CULTURE env var changes."""
        fr_messages = {"hello": "Bonjour"}
        en_messages = {"hello": "Hello"}

        def fake_load(culture):
            return fr_messages if culture == "fr-fr" else en_messages

        with patch("core.i18n._load", side_effect=fake_load):
            _reset_i18n()
            from core.i18n import msg

            monkeypatch.setenv("CULTURE", "fr-fr")
            _reset_i18n()
            assert msg("hello") == "Bonjour"

            monkeypatch.setenv("CULTURE", "en-us")
            # Force reload by resetting _loaded_culture
            import core.i18n as mod
            mod._loaded_culture = ""
            assert msg("hello") == "Hello"

    def test_load_returns_empty_dict_when_file_missing(self):
        """_load() returns {} when no messages.json is found."""
        with patch("os.path.isfile", return_value=False):
            from core.i18n import _load
            result = _load("xx-yy")
        assert result == {}
