"""Validation side-effects — append log, copy approved docs to repo."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Optional

import structlog

from core.config import settings

log = structlog.get_logger(__name__)


def read_file_content(file_path: Optional[str]) -> str:
    """Read markdown content from disk. Returns empty string on failure."""
    if not file_path:
        return ""
    full = (
        os.path.join(settings.ag_flow_root, file_path)
        if not os.path.isabs(file_path)
        else file_path
    )
    try:
        with open(full, encoding="utf-8") as f:
            return f.read()
    except OSError:
        return ""


def append_validation(
    slug: str,
    artifact_id: int,
    key: str,
    verdict: str,
    reviewer: str,
    comment: Optional[str],
) -> None:
    """Append a validation entry to _validations.json on disk."""
    base = os.path.join(settings.ag_flow_root, "projects", slug)
    path = os.path.join(base, "_validations.json")
    entries: list[dict] = []
    if os.path.isfile(path):
        try:
            with open(path, encoding="utf-8") as f:
                entries = json.load(f)
        except (OSError, json.JSONDecodeError):
            entries = []

    entries.append({
        "artifact_id": artifact_id,
        "key": key,
        "verdict": verdict,
        "reviewer": reviewer,
        "comment": comment or "",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })

    os.makedirs(base, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(entries, f, indent=2, ensure_ascii=False)


async def copy_to_repo(
    slug: str,
    key: str,
    file_path: Optional[str],
    category: Optional[str],
    reviewer: str,
) -> None:
    """Copy approved doc deliverable to the project repo and commit."""
    from services.git_service import _run_git

    if not file_path:
        return

    repo = os.path.join(settings.ag_flow_root, "projects", slug, "repo")
    if not os.path.isdir(os.path.join(repo, ".git")):
        log.warning("copy_to_repo_no_git", slug=slug)
        return

    content = read_file_content(file_path)
    if not content:
        return

    cat_folder = (category or "general").replace("/", os.sep)
    dest_dir = os.path.join(repo, "docs", cat_folder)
    os.makedirs(dest_dir, exist_ok=True)
    dest_file = os.path.join(dest_dir, key + ".md")

    with open(dest_file, "w", encoding="utf-8") as f:
        f.write(content)

    await _run_git(repo, "add", dest_file)
    msg = f"docs: add {key} (approved by {reviewer})"
    await _run_git(repo, "commit", "-m", msg)
    await _run_git(repo, "push", "origin", "HEAD")
    log.info("deliverable_copied_to_repo", slug=slug, key=key)
