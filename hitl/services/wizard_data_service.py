"""Wizard data service — persist wizard step data to create-project.json."""

from __future__ import annotations

import json
import os
from typing import Any, Optional

import structlog

from core.config import settings

log = structlog.get_logger(__name__)


def _wizard_path(slug: str) -> str:
    """Return the path to the create-project.json file."""
    return os.path.join(settings.ag_flow_root, "projects", slug, "create-project.json")


async def save_step(slug: str, step_id: int, data: dict[str, Any]) -> list[dict[str, Any]]:
    """Save a wizard step's data to create-project.json.

    Replaces the entry if step_id already exists, appends otherwise.
    Returns the full updated array.
    """
    path = _wizard_path(slug)
    steps: list[dict[str, Any]] = []
    if os.path.isfile(path):
        with open(path, encoding="utf-8") as f:
            steps = json.load(f)

    found = False
    for s in steps:
        if s.get("step_id") == step_id:
            s["data"] = data
            found = True
            break
    if not found:
        steps.append({"step_id": step_id, "data": data})

    steps.sort(key=lambda s: s.get("step_id", 0))

    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(steps, f, ensure_ascii=False, indent=2)

    log.info("wizard_step_saved", slug=slug, step_id=step_id)
    return steps


async def get_wizard_data(slug: str) -> list[dict[str, Any]]:
    """Read all wizard step data."""
    path = _wizard_path(slug)
    if not os.path.isfile(path):
        return []
    with open(path, encoding="utf-8") as f:
        return json.load(f)


async def get_step(slug: str, step_id: int) -> Optional[dict[str, Any]]:
    """Read a single wizard step's data."""
    for s in await get_wizard_data(slug):
        if s.get("step_id") == step_id:
            return s.get("data")
    return None


async def delete_wizard_data(slug: str) -> bool:
    """Delete create-project.json — marks wizard as complete."""
    path = _wizard_path(slug)
    if os.path.isfile(path):
        os.remove(path)
        log.info("wizard_data_deleted", slug=slug)
        return True
    return False
