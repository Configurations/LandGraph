"""Tests for services/deliverable_service.py — list, detail, validate, remarks, update."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest

from tests.conftest import make_record

NOW = datetime(2026, 3, 20, tzinfo=timezone.utc)
TASK_ID = uuid.uuid4()


def _artifact_row(**overrides):
    defaults = dict(
        id=1, task_id=TASK_ID, key="prd", deliverable_type="delivers_docs",
        file_path="projects/demo/artifacts/prd.md", git_branch="temp/prd",
        category="documentation", status="pending", reviewer=None,
        review_comment=None, reviewed_at=None, created_at=NOW,
        agent_id="requirements_analyst", phase="Discovery",
        project_slug="demo",
    )
    defaults.update(overrides)
    return make_record(**defaults)


def _detail_row(**overrides):
    row = _artifact_row(**overrides)
    row["cost_usd"] = overrides.get("cost_usd", 0.05)
    return row


def _remark_row(**overrides):
    defaults = dict(
        id=10, artifact_id=1, reviewer="alice@t.com",
        comment="Looks good", created_at=NOW,
    )
    defaults.update(overrides)
    return make_record(**defaults)


# ── list_deliverables ────────────────────────────────────────

@pytest.mark.asyncio
async def test_list_deliverables_returns_enriched_list():
    rows = [_artifact_row(id=1), _artifact_row(id=2, key="specs")]
    with patch("services.deliverable_service.fetch_all", new_callable=AsyncMock, return_value=rows):
        from services.deliverable_service import list_deliverables
        result = await list_deliverables("demo")
    assert len(result) == 2
    assert result[0].key == "prd"
    assert result[1].key == "specs"
    assert result[0].agent_id == "requirements_analyst"


@pytest.mark.asyncio
async def test_list_deliverables_empty():
    with patch("services.deliverable_service.fetch_all", new_callable=AsyncMock, return_value=[]):
        from services.deliverable_service import list_deliverables
        result = await list_deliverables("demo", phase="Build")
    assert result == []


# ── get_deliverable ──────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_deliverable_found():
    row = _detail_row()
    with (
        patch("services.deliverable_service.fetch_one", new_callable=AsyncMock, return_value=row),
        patch("services.deliverable_service.read_file_content", return_value="# PRD\nContent"),
    ):
        from services.deliverable_service import get_deliverable
        result = await get_deliverable(1)
    assert result is not None
    assert result.content == "# PRD\nContent"
    assert result.cost_usd == 0.05


@pytest.mark.asyncio
async def test_get_deliverable_not_found():
    with patch("services.deliverable_service.fetch_one", new_callable=AsyncMock, return_value=None):
        from services.deliverable_service import get_deliverable
        result = await get_deliverable(999)
    assert result is None


# ── validate_deliverable ─────────────────────────────────────

@pytest.mark.asyncio
async def test_validate_approve_copies_to_repo():
    info_row = make_record(
        key="prd", file_path="artifacts/prd.md",
        deliverable_type="delivers_docs", category="documentation",
        project_slug="demo",
    )
    with (
        patch("services.deliverable_service.execute", new_callable=AsyncMock, return_value="UPDATE 1"),
        patch("services.deliverable_service.fetch_one", new_callable=AsyncMock, return_value=info_row),
        patch("services.deliverable_service.append_validation") as mock_append,
        patch("services.deliverable_service.copy_to_repo", new_callable=AsyncMock) as mock_copy,
    ):
        from services.deliverable_service import validate_deliverable
        ok = await validate_deliverable(1, "approved", "alice@t.com", "LGTM")
    assert ok is True
    mock_append.assert_called_once()
    mock_copy.assert_awaited_once()


@pytest.mark.asyncio
async def test_validate_reject_no_copy():
    info_row = make_record(
        key="prd", file_path="artifacts/prd.md",
        deliverable_type="delivers_docs", category="documentation",
        project_slug="demo",
    )
    with (
        patch("services.deliverable_service.execute", new_callable=AsyncMock, return_value="UPDATE 1"),
        patch("services.deliverable_service.fetch_one", new_callable=AsyncMock, return_value=info_row),
        patch("services.deliverable_service.append_validation") as mock_append,
        patch("services.deliverable_service.copy_to_repo", new_callable=AsyncMock) as mock_copy,
    ):
        from services.deliverable_service import validate_deliverable
        ok = await validate_deliverable(1, "rejected", "bob@t.com", "Needs work")
    assert ok is True
    mock_append.assert_called_once()
    mock_copy.assert_not_awaited()


# ── submit_remark ────────────────────────────────────────────

@pytest.mark.asyncio
async def test_submit_remark():
    row = _remark_row()
    with patch("services.deliverable_service.fetch_one", new_callable=AsyncMock, return_value=row):
        from services.deliverable_service import submit_remark
        result = await submit_remark(1, "alice@t.com", "Looks good")
    assert result.comment == "Looks good"
    assert result.artifact_id == 1


# ── list_remarks ─────────────────────────────────────────────

@pytest.mark.asyncio
async def test_list_remarks():
    rows = [_remark_row(id=10), _remark_row(id=11, comment="Fix typo")]
    with patch("services.deliverable_service.fetch_all", new_callable=AsyncMock, return_value=rows):
        from services.deliverable_service import list_remarks
        result = await list_remarks(1)
    assert len(result) == 2
    assert result[1].comment == "Fix typo"


# ── update_content ───────────────────────────────────────────

@pytest.mark.asyncio
async def test_update_content_writes_to_disk(tmp_path):
    fp = str(tmp_path / "prd.md")
    row = make_record(file_path=fp)
    with patch("services.deliverable_service.fetch_one", new_callable=AsyncMock, return_value=row):
        from services.deliverable_service import update_content
        ok = await update_content(1, "# Updated PRD")
    assert ok is True
    assert (tmp_path / "prd.md").read_text(encoding="utf-8") == "# Updated PRD"
