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

    # Mock OnboardingConfig
    mock_onboarding = MagicMock()
    mock_onboarding.error = ""
    mock_onboarding.system_prompt = "test prompt"
    mock_onboarding.agent_prompts = {}
    mock_onboarding.agent_tools = {}
    mock_onboarding.agents = []

    with (
        patch("services.analysis_service._resolve_orchestrator", new_callable=AsyncMock,
              return_value={"agent_id": "orchestrator", "name": "Orch"}),
        patch("services.analysis_service.fetch_one", new_callable=AsyncMock,
              side_effect=[
                  make_record(name="My Project"),  # SELECT pm_projects (project name)
                  make_record(id=1),                # INSERT project_workflows
                  make_record(id=10),               # INSERT workflow_phases
                  make_record(id="abc-123"),         # INSERT dispatcher_tasks
              ]),
        patch("services.analysis_service.load_teams",
              return_value=[{"id": "team1", "name": "Team 1", "directory": "Team1"}]),
        patch("services.analysis_service.execute", new_callable=AsyncMock) as mock_exec,
        patch("services.analysis_service._load_onboarding_config", new_callable=AsyncMock,
              return_value=mock_onboarding),
        patch("services.analysis_service._load_deduced_prompt", new_callable=AsyncMock,
              return_value="test instruction"),
        patch("os.path.isdir", return_value=False),
        patch("services.analysis_service.httpx.AsyncClient") as MockClient,
    ):
        ctx = AsyncMock()
        ctx.post.return_value = mock_resp
        MockClient.return_value.__aenter__ = AsyncMock(return_value=ctx)
        MockClient.return_value.__aexit__ = AsyncMock(return_value=False)

        from services.analysis_service import start_analysis
        result = await start_analysis("my-project", "team1")

    assert result["agent_id"] == "orchestrator"
    assert result["workflow_id"] is not None
    # Verify DB updates were called (workflow + phase + task + pm_projects)
    assert mock_exec.call_count >= 1


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
                  make_record(analysis_task_id="abc", analysis_status="in_progress", onboarding_workflow_id=None),
                  None,  # no pending question in _sync_status
                  make_record(status="success"),  # dispatcher_task status
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

    with (
        patch("services.analysis_service.fetch_one", new_callable=AsyncMock,
              return_value=make_record(team_id="team1", onboarding_workflow_id=None)),
        patch("services.analysis_service.fetch_all", new_callable=AsyncMock,
              side_effect=[events, hitl, conv]),
        patch("services.analysis_service.load_teams", return_value=[]),
    ):
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

    mock_onboarding = MagicMock()
    mock_onboarding.error = ""
    mock_onboarding.system_prompt = "test"
    mock_onboarding.agent_prompts = {}
    mock_onboarding.agent_tools = {}
    mock_onboarding.agents = []

    with (
        patch("services.analysis_service.execute", new_callable=AsyncMock),
        patch("services.analysis_service.fetch_one", new_callable=AsyncMock,
              side_effect=[
                  make_record(team_id="team1", analysis_task_id="old-task", onboarding_workflow_id=None),
                  None,  # no final question pending
                  make_record(name="My Project"),  # project name
              ]),
        patch("services.analysis_service._load_onboarding_config", new_callable=AsyncMock,
              return_value=mock_onboarding),
        patch("services.analysis_service._resolve_embedding_provider_async", new_callable=AsyncMock,
              return_value=""),
        patch("services.rag_service.search", new_callable=AsyncMock, return_value=[]),
        patch("services.analysis_service.load_json_config", return_value={"default": "", "providers": {}}),
        patch("services.analysis_service.httpx.AsyncClient") as MockClient,
    ):
        ctx = AsyncMock()
        mock_run.json.return_value = {"output": "ok", "decisions": [], "agents_dispatched": []}
        ctx.post.return_value = mock_run
        MockClient.return_value.__aenter__ = AsyncMock(return_value=ctx)
        MockClient.return_value.__aexit__ = AsyncMock(return_value=False)

        from services.analysis_service import send_free_message
        result = await send_free_message("my-project", "More context here", "alice@test.com")

    assert result.get("task_id") is not None or result.get("ok") is True


# ── start_analysis — workflow creation ─────────────────────────


@pytest.mark.asyncio
async def test_start_analysis_creates_workflow_and_phase():
    """start_analysis should INSERT into project_workflows + workflow_phases."""
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"task_id": "abc-123"}
    mock_resp.raise_for_status = MagicMock()

    # Track all execute/fetch_one calls
    exec_calls = []
    fetch_one_returns = [
        # 1: SELECT name FROM pm_projects
        make_record(name="My Project"),
        # 2: INSERT INTO project_workflows RETURNING id
        make_record(id=99),
        # 3: INSERT INTO workflow_phases RETURNING id
        make_record(id=501),
        # 4: INSERT INTO dispatcher_tasks RETURNING id
        make_record(id="task-uuid"),
    ]
    fetch_idx = {"i": 0}

    async def _fake_fetch_one(query, *args):
        idx = fetch_idx["i"]
        fetch_idx["i"] += 1
        return fetch_one_returns[idx] if idx < len(fetch_one_returns) else None

    async def _fake_execute(query, *args):
        exec_calls.append((query, args))

    # Create a proper mock for OnboardingConfig
    from services.analysis_service import OnboardingConfig
    onboarding = OnboardingConfig()
    onboarding.system_prompt = "test prompt"
    onboarding.agents = ["orchestrator"]

    with (
        patch("services.analysis_service._resolve_orchestrator", new_callable=AsyncMock,
              return_value={"agent_id": "orchestrator", "name": "Orch"}),
        patch("services.analysis_service.fetch_one", new_callable=AsyncMock,
              side_effect=_fake_fetch_one),
        patch("services.analysis_service.load_teams",
              return_value=[{"id": "team1", "name": "Team 1", "directory": "Team1"}]),
        patch("services.analysis_service.execute", new_callable=AsyncMock,
              side_effect=_fake_execute),
        patch("os.path.isdir", return_value=False),
        patch("services.analysis_service._load_onboarding_config", new_callable=AsyncMock,
              return_value=onboarding),
        patch("services.analysis_service._load_deduced_prompt", new_callable=AsyncMock,
              return_value=""),
        patch("services.analysis_service._run_analysis_pipeline", new_callable=AsyncMock),
    ):
        from services.analysis_service import start_analysis
        result = await start_analysis("my-project", "team1")

    assert result["workflow_id"] == 99
    assert result["task_id"] == "task-uuid"
    # Verify UPDATE pm_projects with onboarding_workflow_id was called
    update_calls = [c for c in exec_calls if "onboarding_workflow_id" in c[0]]
    assert len(update_calls) >= 1


@pytest.mark.asyncio
async def test_start_analysis_sets_onboarding_workflow_id():
    """start_analysis should UPDATE pm_projects with onboarding_workflow_id."""
    exec_calls = []
    fetch_one_returns = [
        make_record(name="My Project"),
        make_record(id=77),   # workflow
        make_record(id=301),  # phase
        make_record(id="t-1"),  # task
    ]
    fetch_idx = {"i": 0}

    async def _fake_fetch_one(query, *args):
        idx = fetch_idx["i"]
        fetch_idx["i"] += 1
        return fetch_one_returns[idx] if idx < len(fetch_one_returns) else None

    async def _fake_execute(query, *args):
        exec_calls.append((query, args))

    from services.analysis_service import OnboardingConfig
    onboarding = OnboardingConfig()
    onboarding.agents = ["orchestrator"]

    with (
        patch("services.analysis_service._resolve_orchestrator", new_callable=AsyncMock,
              return_value={"agent_id": "orchestrator", "name": "Orch"}),
        patch("services.analysis_service.fetch_one", new_callable=AsyncMock,
              side_effect=_fake_fetch_one),
        patch("services.analysis_service.load_teams",
              return_value=[{"id": "team1", "name": "Team 1", "directory": "Team1"}]),
        patch("services.analysis_service.execute", new_callable=AsyncMock,
              side_effect=_fake_execute),
        patch("os.path.isdir", return_value=False),
        patch("services.analysis_service._load_onboarding_config", new_callable=AsyncMock,
              return_value=onboarding),
        patch("services.analysis_service._load_deduced_prompt", new_callable=AsyncMock,
              return_value=""),
        patch("services.analysis_service._run_analysis_pipeline", new_callable=AsyncMock),
    ):
        from services.analysis_service import start_analysis
        result = await start_analysis("my-project", "team1")

    # Find the UPDATE that sets onboarding_workflow_id
    update_calls = [c for c in exec_calls if "onboarding_workflow_id" in c[0]]
    assert len(update_calls) == 1
    # The workflow_id=77 should be in the args
    assert 77 in update_calls[0][1]


# ── get_analysis_status — workflow_id ──────────────────────────


@pytest.mark.asyncio
async def test_get_analysis_status_returns_workflow_id():
    """get_analysis_status should include workflow_id in the response."""
    with patch("services.analysis_service.fetch_one", new_callable=AsyncMock,
               side_effect=[
                   make_record(analysis_task_id="abc", analysis_status="completed",
                               onboarding_workflow_id=42),
                   None,  # pending question check
               ]):
        from services.analysis_service import get_analysis_status
        result = await get_analysis_status("my-project")

    assert result["workflow_id"] == 42
    assert result["task_id"] == "abc"


@pytest.mark.asyncio
async def test_get_analysis_status_uses_workflow_thread_id():
    """When onboarding_workflow_id is set, thread_id for pending check = 'workflow-{id}'."""
    fetch_calls = []

    async def _fake_fetch_one(query, *args):
        fetch_calls.append((query, args))
        if "pm_projects" in query:
            return make_record(analysis_task_id="abc", analysis_status="completed",
                               onboarding_workflow_id=42)
        return None  # no pending question

    with patch("services.analysis_service.fetch_one", new_callable=AsyncMock,
               side_effect=_fake_fetch_one):
        from services.analysis_service import get_analysis_status
        result = await get_analysis_status("my-project")

    # The second query (hitl_requests) should use workflow-42 as thread_id
    hitl_calls = [c for c in fetch_calls if "hitl_requests" in c[0]]
    assert len(hitl_calls) == 1
    assert hitl_calls[0][1][0] == "workflow-42"


# ── send_free_message — workflow thread_id ─────────────────────


@pytest.mark.asyncio
async def test_send_free_message_uses_workflow_thread_id():
    """When onboarding_workflow_id is set, send_free_message uses 'workflow-{id}' thread."""
    from services.analysis_service import OnboardingConfig

    onboarding = OnboardingConfig()
    onboarding.system_prompt = "test"
    onboarding.agents = ["orchestrator"]

    mock_resp = MagicMock()
    mock_resp.json.return_value = {"task_id": "new-task"}
    mock_resp.raise_for_status = MagicMock()

    with (
        patch("services.analysis_service.execute", new_callable=AsyncMock),
        patch("services.analysis_service.fetch_one", new_callable=AsyncMock,
              side_effect=[
                  # 1: SELECT pm_projects
                  make_record(team_id="team1", analysis_task_id="old-task",
                              onboarding_workflow_id=55),
                  # 2: SELECT hitl_requests (final check)
                  None,
                  # 3: SELECT current_phase_id from project_workflows
                  make_record(current_phase_id=100),
                  # 4: SELECT name from pm_projects (for _resolve)
                  make_record(name="My Project"),
              ]),
        patch("services.analysis_service.get_conversation", new_callable=AsyncMock, return_value=[]),
        patch("services.analysis_service._resolve_orchestrator", new_callable=AsyncMock,
              return_value={"agent_id": "orchestrator", "name": "Orch"}),
        patch("services.analysis_service._load_onboarding_config", new_callable=AsyncMock,
              return_value=onboarding),
        patch("services.analysis_service._resolve_embedding_provider_async", new_callable=AsyncMock,
              return_value=""),
        patch("services.analysis_service.load_json_config", return_value={"default": "", "providers": {}}),
        patch("services.rag_service.search", new_callable=AsyncMock, return_value=[]),
        patch("services.analysis_service.httpx.AsyncClient") as MockClient,
    ):
        ctx = AsyncMock()
        ctx.post.return_value = mock_resp
        MockClient.return_value.__aenter__ = AsyncMock(return_value=ctx)
        MockClient.return_value.__aexit__ = AsyncMock(return_value=False)

        from services.analysis_service import send_free_message
        result = await send_free_message("my-project", "More info", "alice@test.com")

    # Verify the invoke payload uses workflow-55 as thread_id
    call_args = ctx.post.call_args
    payload = call_args.kwargs.get("json") or call_args[1].get("json")
    assert payload["thread_id"] == "workflow-55"
