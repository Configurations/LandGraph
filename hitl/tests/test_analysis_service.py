"""Tests for services/analysis_service.py — orchestrator analysis conversation."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, mock_open, patch

import httpx
import pytest

from tests.conftest import make_record


# ── _resolve_orchestrator ───────────────────────────────────────


@pytest.mark.asyncio
async def test_resolve_orchestrator_found():
    registry = {
        "agents": {
            "orchestrator": {"name": "Orchestrateur", "type": "orchestrator"},
            "lead_dev": {"name": "Lead Dev", "type": "single"},
        }
    }
    with (
        patch("services.analysis_service.load_teams", return_value=[{"id": "team1", "directory": "Team1"}]),
        patch("services.analysis_service._find_config_dir", return_value="/app/config"),
        patch("os.path.isfile", return_value=True),
        patch("builtins.open", mock_open(read_data=json.dumps(registry))),
    ):
        from services.analysis_service import _resolve_orchestrator
        result = await _resolve_orchestrator("team1")

    assert result["agent_id"] == "orchestrator"
    assert result["name"] == "Orchestrateur"


@pytest.mark.asyncio
async def test_resolve_orchestrator_not_found():
    registry = {"agents": {"lead_dev": {"name": "Lead Dev", "type": "single"}}}
    with (
        patch("services.analysis_service.load_teams", return_value=[{"id": "team1", "directory": "Team1"}]),
        patch("services.analysis_service._find_config_dir", return_value="/app/config"),
        patch("os.path.isfile", return_value=True),
        patch("builtins.open", mock_open(read_data=json.dumps(registry))),
    ):
        from services.analysis_service import _resolve_orchestrator
        with pytest.raises(ValueError, match="No orchestrator"):
            await _resolve_orchestrator("team1")


# ── start_analysis ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_start_analysis_dispatches_task():
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"task_id": "abc-123"}
    mock_resp.raise_for_status = MagicMock()

    with (
        patch("services.analysis_service._resolve_orchestrator", new_callable=AsyncMock,
              return_value={"agent_id": "orchestrator", "name": "Orch"}),
        patch("services.analysis_service.fetch_one", new_callable=AsyncMock,
              return_value=make_record(name="My Project")),
        patch("services.analysis_service.load_teams",
              return_value=[{"id": "team1", "name": "Team 1", "directory": "Team1"}]),
        patch("services.analysis_service.execute", new_callable=AsyncMock) as mock_exec,
        patch("os.path.isdir", return_value=False),
        patch("services.analysis_service.httpx.AsyncClient") as MockClient,
    ):
        ctx = AsyncMock()
        ctx.post.return_value = mock_resp
        MockClient.return_value.__aenter__ = AsyncMock(return_value=ctx)
        MockClient.return_value.__aexit__ = AsyncMock(return_value=False)

        from services.analysis_service import start_analysis
        result = await start_analysis("my-project", "team1")

    assert result["task_id"] == "abc-123"
    assert result["agent_id"] == "orchestrator"
    # Verify the dispatched payload uses onboarding thread
    call_args = ctx.post.call_args
    payload = call_args.kwargs.get("json") or call_args[1].get("json")
    assert payload["thread_id"] == "onboarding-my-project"
    assert payload["agent_id"] == "orchestrator"
    # Verify DB update
    mock_exec.assert_called_once()


# ── get_analysis_status ─────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_status_not_started():
    with patch("services.analysis_service.fetch_one", new_callable=AsyncMock,
               return_value=make_record(analysis_task_id=None, analysis_status="not_started")):
        from services.analysis_service import get_analysis_status
        result = await get_analysis_status("my-project")

    assert result["status"] == "not_started"
    assert result["task_id"] is None


@pytest.mark.asyncio
async def test_get_status_syncs_with_dispatcher():
    mock_task_resp = MagicMock()
    mock_task_resp.json.return_value = {"status": "success"}
    mock_task_resp.raise_for_status = MagicMock()

    with (
        patch("services.analysis_service.fetch_one", new_callable=AsyncMock,
              side_effect=[
                  make_record(analysis_task_id="abc", analysis_status="in_progress"),
                  None,  # no pending question in _sync_status
                  None,  # no pending question in get_analysis_status
              ]),
        patch("services.analysis_service.execute", new_callable=AsyncMock),
        patch("services.analysis_service.httpx.AsyncClient") as MockClient,
    ):
        ctx = AsyncMock()
        ctx.get.return_value = mock_task_resp
        MockClient.return_value.__aenter__ = AsyncMock(return_value=ctx)
        MockClient.return_value.__aexit__ = AsyncMock(return_value=False)

        from services.analysis_service import get_analysis_status
        result = await get_analysis_status("my-project")

    assert result["status"] == "completed"


# ── get_conversation ────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_conversation_merges_sources():
    now = datetime(2026, 3, 24, 10, 0, 0, tzinfo=timezone.utc)
    later = datetime(2026, 3, 24, 10, 1, 0, tzinfo=timezone.utc)
    latest = datetime(2026, 3, 24, 10, 2, 0, tzinfo=timezone.utc)

    events = [make_record(id=1, event_type="progress", data={"data": "Analysing..."}, created_at=now)]
    hitl = [make_record(id="uuid-1", prompt="Budget?", response="50k", status="answered",
                        created_at=later, answered_at=latest)]
    conv = [make_record(id=10, sender="user", content="extra info", created_at=latest)]

    with patch("services.analysis_service.fetch_all", new_callable=AsyncMock,
               side_effect=[events, hitl, conv]):
        from services.analysis_service import get_conversation
        result = await get_conversation("my-project")

    # Should have: 1 progress + 1 question + 1 answer + 1 free message = 4
    assert len(result) == 4
    assert result[0].type == "progress"
    assert result[1].type == "question"
    assert result[2].type == "reply"  # answer or free message (same timestamp)


# ── reply_to_question ───────────────────────────────────────────


@pytest.mark.asyncio
async def test_reply_to_question_success():
    with (
        patch("services.analysis_service.fetch_one", new_callable=AsyncMock,
              return_value=make_record(id="uuid-1", thread_id="onboarding-my-project", status="pending")),
        patch("services.analysis_service.execute", new_callable=AsyncMock) as mock_exec,
    ):
        from services.analysis_service import reply_to_question
        result = await reply_to_question("my-project", "uuid-1", "50k EUR", "alice@test.com")

    assert result["ok"] is True
    assert mock_exec.call_count == 2  # UPDATE hitl_requests + UPDATE pm_projects


@pytest.mark.asyncio
async def test_reply_wrong_thread():
    with patch("services.analysis_service.fetch_one", new_callable=AsyncMock,
               return_value=make_record(id="uuid-1", thread_id="other-thread", status="pending")):
        from services.analysis_service import reply_to_question
        with pytest.raises(ValueError, match="does not belong"):
            await reply_to_question("my-project", "uuid-1", "50k", "alice@test.com")


# ── send_free_message ───────────────────────────────────────────


@pytest.mark.asyncio
async def test_send_free_message_cancels_and_relaunches():
    mock_cancel = MagicMock()
    mock_cancel.raise_for_status = MagicMock()
    mock_run = MagicMock()
    mock_run.json.return_value = {"task_id": "new-task-id"}
    mock_run.raise_for_status = MagicMock()

    with (
        patch("services.analysis_service.execute", new_callable=AsyncMock),
        patch("services.analysis_service.fetch_one", new_callable=AsyncMock,
              return_value=make_record(team_id="team1", analysis_task_id="old-task")),
        patch("services.analysis_service.get_conversation", new_callable=AsyncMock, return_value=[]),
        patch("services.analysis_service._resolve_orchestrator", new_callable=AsyncMock,
              return_value={"agent_id": "orchestrator", "name": "Orch"}),
        patch("services.analysis_service.httpx.AsyncClient") as MockClient,
    ):
        ctx = AsyncMock()
        ctx.post.side_effect = [mock_cancel, mock_run]
        MockClient.return_value.__aenter__ = AsyncMock(return_value=ctx)
        MockClient.return_value.__aexit__ = AsyncMock(return_value=False)

        from services.analysis_service import send_free_message
        result = await send_free_message("my-project", "More context here", "alice@test.com")

    assert result["task_id"] == "new-task-id"
    # Should have called cancel + run
    assert ctx.post.call_count == 2
