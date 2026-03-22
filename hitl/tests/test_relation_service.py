"""Tests for services/relation_service.py."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tests.conftest import FakeRecord, make_record


NOW = datetime(2026, 3, 22, 12, 0, tzinfo=timezone.utc)


def _rel_row(**overrides) -> FakeRecord:
    defaults = dict(
        id=1,
        type="blocks",
        issue_id="TEAM-002",
        issue_title="Backend API",
        issue_status="todo",
        reason="Needs schema first",
        created_by="alice@test.com",
        created_at=NOW,
    )
    defaults.update(overrides)
    return make_record(**defaults)


# ── create_relation ───────────────────────────────────────────

@pytest.mark.asyncio
@patch("services.relation_service.execute", new_callable=AsyncMock)
@patch("services.relation_service.fetch_one", new_callable=AsyncMock)
@patch("services.inbox_service.execute", new_callable=AsyncMock)
async def test_create_relation_inserts(mock_inbox_exec, mock_fetch, mock_exec):
    """create_relation inserts a row and returns RelationResponse."""
    from schemas.relation import RelationCreate
    from services.relation_service import create_relation

    insert_row = make_record(id=1, type="blocks", issue_id="TEAM-002",
                             reason="dep", created_by="alice@test.com", created_at=NOW)
    target_row = make_record(title="Backend", status="todo")
    target_assignee = make_record(assignee="bob@test.com")
    source_row = make_record(project_id=1)

    mock_fetch.side_effect = [insert_row, target_row, target_assignee, source_row]

    data = RelationCreate(type="blocks", target_issue_id="TEAM-002", reason="dep")
    result = await create_relation("TEAM-001", data, "alice@test.com")

    assert result.id == 1
    assert result.type == "blocks"
    assert result.direction == "outgoing"
    assert result.display_type == "Blocks"


@pytest.mark.asyncio
async def test_create_relation_self_reference_blocked():
    """create_relation raises ValueError for self-reference."""
    from schemas.relation import RelationCreate
    from services.relation_service import create_relation

    data = RelationCreate(type="blocks", target_issue_id="TEAM-001")
    with pytest.raises(ValueError, match="self_relation"):
        await create_relation("TEAM-001", data, "alice@test.com")


# ── list_relations ────────────────────────────────────────────

@pytest.mark.asyncio
@patch("services.relation_service.fetch_all", new_callable=AsyncMock)
async def test_list_relations_outgoing_and_incoming(mock_fetch_all):
    """list_relations combines outgoing and incoming relations."""
    from services.relation_service import list_relations

    outgoing = [_rel_row(type="blocks")]
    incoming = [_rel_row(id=2, type="blocks", issue_id="TEAM-003")]
    mock_fetch_all.side_effect = [outgoing, incoming]

    result = await list_relations("TEAM-001")
    assert len(result) == 2
    assert result[0].direction == "outgoing"
    assert result[0].display_type == "Blocks"
    assert result[1].direction == "incoming"
    assert result[1].display_type == "Blocked by"


# ── delete_relation ───────────────────────────────────────────

@pytest.mark.asyncio
@patch("services.relation_service.execute", new_callable=AsyncMock)
@patch("services.relation_service.fetch_one", new_callable=AsyncMock)
@patch("services.inbox_service.execute", new_callable=AsyncMock)
async def test_delete_relation_removes(mock_inbox_exec, mock_fetch, mock_exec):
    """delete_relation removes the row."""
    from services.relation_service import delete_relation

    rel = make_record(id=1, type="relates-to", source_issue_id="TEAM-001",
                      target_issue_id="TEAM-002")
    mock_fetch.return_value = rel

    ok = await delete_relation(1, "alice@test.com")
    assert ok is True
    mock_exec.assert_awaited()


@pytest.mark.asyncio
@patch("services.relation_service.execute", new_callable=AsyncMock)
@patch("services.relation_service.fetch_one", new_callable=AsyncMock)
@patch("services.inbox_service.execute", new_callable=AsyncMock)
async def test_delete_blocks_sends_unblock_notification(
    mock_inbox_exec, mock_fetch, mock_exec,
):
    """Deleting a 'blocks' relation sends unblock notification."""
    from services.relation_service import delete_relation

    rel = make_record(id=1, type="blocks", source_issue_id="TEAM-001",
                      target_issue_id="TEAM-002")
    still_blocked_none = None
    target_issue = make_record(assignee="charlie@test.com")

    mock_fetch.side_effect = [rel, still_blocked_none, target_issue]

    ok = await delete_relation(1, "alice@test.com")
    assert ok is True
    mock_inbox_exec.assert_awaited()


@pytest.mark.asyncio
@patch("services.relation_service.fetch_one", new_callable=AsyncMock)
async def test_delete_relation_not_found(mock_fetch):
    """delete_relation returns False for missing relation."""
    from services.relation_service import delete_relation

    mock_fetch.return_value = None
    ok = await delete_relation(999, "alice@test.com")
    assert ok is False


# ── bulk_create ───────────────────────────────────────────────

@pytest.mark.asyncio
@patch("services.relation_service.create_relation", new_callable=AsyncMock)
async def test_bulk_create_multiple(mock_create):
    """bulk_create calls create_relation for each item."""
    from schemas.relation import RelationCreate
    from services.relation_service import bulk_create

    mock_create.return_value = MagicMock()

    items = [
        RelationCreate(type="blocks", target_issue_id="TEAM-002"),
        RelationCreate(type="relates-to", target_issue_id="TEAM-003"),
    ]
    results = await bulk_create("TEAM-001", items, "alice@test.com")
    assert len(results) == 2
    assert mock_create.await_count == 2
