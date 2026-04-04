"""Tests for routes/hitl.py + services/hitl_service.py."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest
from httpx import AsyncClient

from core.security import encode_token
from tests.conftest import SAMPLE_USER_ID, make_record, set_fetch, set_fetchrow


MEMBER_TOKEN = encode_token(str(SAMPLE_USER_ID), "m@t.com", "member", ["team1"])
ADMIN_TOKEN = encode_token(str(SAMPLE_USER_ID), "a@t.com", "admin", ["team1"])

NOW = datetime(2026, 3, 20, 10, 0, 0, tzinfo=timezone.utc)


def _question_row(**overrides):
    defaults = dict(
        id=uuid.uuid4(),
        thread_id="thread-1",
        agent_id="lead_dev",
        team_id="team1",
        request_type="approval",
        prompt="Approve PRD?",
        context=None,
        channel="discord",
        status="pending",
        response=None,
        reviewer=None,
        created_at=NOW,
        answered_at=None,
    )
    defaults.update(overrides)
    return make_record(**defaults)


# ── GET /api/teams/{id}/questions ──────────────────────────────

@pytest.mark.asyncio
async def test_list_questions(app_client: AsyncClient, mock_pool: AsyncMock):
    mock_pool.fetch.return_value = [_question_row(), _question_row()]

    resp = await app_client.get("/api/teams/team1/questions", headers={
        "Authorization": f"Bearer {MEMBER_TOKEN}",
    })
    assert resp.status_code == 200
    assert len(resp.json()) == 2


@pytest.mark.asyncio
async def test_list_questions_filter_status(app_client: AsyncClient, mock_pool: AsyncMock):
    mock_pool.fetch.return_value = [_question_row(status="pending")]

    resp = await app_client.get(
        "/api/teams/team1/questions?status=pending",
        headers={"Authorization": f"Bearer {MEMBER_TOKEN}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["status"] == "pending"


# ── GET /api/teams/{id}/questions/stats ────────────────────────

@pytest.mark.asyncio
async def test_get_stats(app_client: AsyncClient, mock_pool: AsyncMock):
    mock_pool.fetch.return_value = [
        make_record(status="pending", cnt=5),
        make_record(status="answered", cnt=3),
    ]

    resp = await app_client.get("/api/teams/team1/questions/stats", headers={
        "Authorization": f"Bearer {MEMBER_TOKEN}",
    })
    assert resp.status_code == 200
    body = resp.json()
    assert body["pending"] == 5
    assert body["answered"] == 3
    assert body["total"] == 8


# ── POST /api/questions/{id}/answer ────────────────────────────

@pytest.mark.asyncio
async def test_answer_question_success(app_client: AsyncClient, mock_pool: AsyncMock):
    qid = uuid.uuid4()
    mock_pool.fetchrow.return_value = make_record(
        id=qid, status="pending", thread_id="test-thread", request_type="question",
    )

    resp = await app_client.post(f"/api/questions/{qid}/answer", json={
        "response": "Looks good", "action": "approve",
    }, headers={"Authorization": f"Bearer {MEMBER_TOKEN}"})

    assert resp.status_code == 200
    assert resp.json()["ok"] is True


@pytest.mark.asyncio
async def test_answer_already_answered(app_client: AsyncClient, mock_pool: AsyncMock):
    qid = uuid.uuid4()
    mock_pool.fetchrow.return_value = make_record(
        id=qid, status="answered", thread_id="test-thread", request_type="question",
    )

    resp = await app_client.post(f"/api/questions/{qid}/answer", json={
        "response": "too late", "action": "answer",
    }, headers={"Authorization": f"Bearer {MEMBER_TOKEN}"})

    assert resp.status_code == 409


# ── GET /api/questions/{id} ────────────────────────────────────

@pytest.mark.asyncio
async def test_get_question_not_found(app_client: AsyncClient, mock_pool: AsyncMock):
    mock_pool.fetchrow.return_value = None
    qid = uuid.uuid4()

    resp = await app_client.get(f"/api/questions/{qid}", headers={
        "Authorization": f"Bearer {MEMBER_TOKEN}",
    })
    assert resp.status_code == 404


# ── answer_question — onboarding relaunch detection ───────────


@pytest.mark.asyncio
async def test_answer_question_relaunches_onboarding_by_workflow_type():
    """thread_id='workflow-42', DB returns workflow_type='onboarding' → relaunch."""
    from unittest.mock import patch, AsyncMock as _AM

    qid = uuid.uuid4()
    wf_row = make_record(workflow_type="onboarding", project_slug="my-project")

    with (
        patch("services.hitl_service.fetch_one", new_callable=_AM, side_effect=[
            # 1st call: SELECT hitl_requests
            make_record(id=qid, status="pending", thread_id="workflow-42", request_type="question"),
            # 2nd call: SELECT project_workflows
            wf_row,
        ]),
        patch("services.hitl_service.execute", new_callable=_AM),
        patch("services.analysis_service.send_free_message", new_callable=_AM) as mock_send,
    ):
        from services.hitl_service import answer_question
        result = await answer_question(qid, "Looks good", "answer", "alice@test.com")

    assert result.ok is True
    assert mock_send.called


@pytest.mark.asyncio
async def test_answer_question_relaunches_onboarding_by_legacy_thread():
    """thread_id='onboarding-my-project' → relaunch via legacy detection."""
    from unittest.mock import patch, AsyncMock as _AM

    qid = uuid.uuid4()

    with (
        patch("services.hitl_service.fetch_one", new_callable=_AM, return_value=make_record(
            id=qid, status="pending", thread_id="onboarding-my-project", request_type="question",
        )),
        patch("services.hitl_service.execute", new_callable=_AM),
        patch("services.analysis_service.send_free_message", new_callable=_AM) as mock_send,
    ):
        from services.hitl_service import answer_question
        result = await answer_question(qid, "50k EUR", "answer", "alice@test.com")

    assert result.ok is True
    mock_send.assert_called_once()
    call_args = mock_send.call_args
    assert call_args[0][0] == "my-project"  # project_slug extracted from thread_id


@pytest.mark.asyncio
async def test_answer_question_skips_relaunch_for_non_onboarding():
    """thread_id='workflow-42', DB returns workflow_type='development' → no relaunch."""
    from unittest.mock import patch, AsyncMock as _AM

    qid = uuid.uuid4()
    wf_row = make_record(workflow_type="development", project_slug="my-project")

    with (
        patch("services.hitl_service.fetch_one", new_callable=_AM, side_effect=[
            make_record(id=qid, status="pending", thread_id="workflow-42", request_type="question"),
            wf_row,
        ]),
        patch("services.hitl_service.execute", new_callable=_AM),
        patch("services.analysis_service.send_free_message", new_callable=_AM) as mock_send,
    ):
        from services.hitl_service import answer_question
        result = await answer_question(qid, "Done", "answer", "alice@test.com")

    assert result.ok is True
    mock_send.assert_not_called()


@pytest.mark.asyncio
async def test_answer_question_skips_relaunch_for_approval():
    """request_type='approval' → should NOT relaunch even if onboarding thread."""
    from unittest.mock import patch, AsyncMock as _AM

    qid = uuid.uuid4()

    with (
        patch("services.hitl_service.fetch_one", new_callable=_AM, return_value=make_record(
            id=qid, status="pending", thread_id="onboarding-my-project", request_type="approval",
        )),
        patch("services.hitl_service.execute", new_callable=_AM),
        patch("services.analysis_service.send_free_message", new_callable=_AM) as mock_send,
    ):
        from services.hitl_service import answer_question
        result = await answer_question(qid, "approved", "approve", "alice@test.com")

    assert result.ok is True
    mock_send.assert_not_called()
