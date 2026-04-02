"""Minimal backend i18n — loads messages from Models/{culture}/messages.json."""

import json
import os
from typing import Any

_messages: dict[str, str] = {}
_loaded_culture: str = ""


def _load(culture: str) -> dict[str, str]:
    """Load messages.json for a culture, searching config/ then Shared/."""
    for base in ["/app/config", "/app/Shared", "config", "Shared"]:
        path = os.path.join(base, "Models", culture, "messages.json")
        if os.path.isfile(path):
            with open(path, encoding="utf-8") as f:
                return json.load(f)
    return {}


def msg(key: str, **kwargs: Any) -> str:
    """Get a translated message. Reloads on first call or culture change."""
    global _messages, _loaded_culture
    culture = os.getenv("CULTURE", "fr-fr")
    if culture != _loaded_culture:
        _messages = _load(culture)
        _loaded_culture = culture
    template = _messages.get(key, key)
    if kwargs:
        try:
            return template.format(**kwargs)
        except (KeyError, IndexError):
            return template
    return template
