"""Tests for services.hitl_bridge — HITL question creation and wait."""

from __future__ import annotations

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID

from models.task import QuestionEvent, Task, TaskPayload
from services.hitl_bridge import HitlBridge
from core.events import HitlResponseWaiter


TASK_ID = UUID("aabbccdd-1122-3344-5566-778899aabbcc")


@pytest.fixture
def task():
    return Task(
        task_id=TASK_ID,
        agent_id="requirements_analyst",
        team_id="team1",
        thread_id="thread-99",
        phase="discovery",
        iteration=1,
        payload=TaskPayload(instruction="Analyse requirements"),
    )


@pytest.fixture
def question():
    return QuestionEvent(
        task_id=str(TASK_ID),
        prompt="Should we include mobile?",
        context={"scope": "mvp"},
    )


@pytest.fixture
def waiter():
    return HitlResponseWaiter()


@pytest.fixture
def bridge(mock_pool, waiter):
    return HitlBridge(pool=mock_pool, waiter=waiter)


# ── ask ──────────────────────────────────────────────


class TestAsk:
    @pytest.mark.asyncio
    async def test_ask_returns_response_text(self, bridge, task, question, waiter, mock_pool):
        # Simulate a response arriving via the waiter
        async def fake_wait(request_id, timeout):
            return {"response": "Yes, include mobile", "reviewer": "admin@test.com"}

        waiter.wait_for = AsyncMock(side_effect=fake_wait)

        with patch("services.hitl_bridge.pg_notify", new_callable=AsyncMock) as mock_notify:
            result = await bridge.ask(task, question, timeout=60.0)

        assert result == "Yes, include mobile"

    @pytest.mark.asyncio
    async def test_ask_inserts_request_into_db(self, bridge, task, question, waiter, mock_pool):
        waiter.wait_for = AsyncMock(return_value={"response": "ok"})

        with patch("services.hitl_bridge.pg_notify", new_callable=AsyncMock):
            await bridge.ask(task, question, timeout=60.0)

        # _insert_request calls pool.execute
        mock_pool.execute.assert_called_once()
        sql = mock_pool.execute.call_args[0][0]
        assert "hitl_requests" in sql
        # Check agent_id and team_id are passed
        args = mock_pool.execute.call_args[0]
        assert args[3] == "requirements_analyst"  # agent_id
        assert args[4] == "team1"                 # team_id

    @pytest.mark.asyncio
    async def test_ask_sends_pg_notify(self, bridge, task, question, waiter, mock_pool):
        waiter.wait_for = AsyncMock(return_value={"response": "no"})

        with patch("services.hitl_bridge.pg_notify", new_callable=AsyncMock) as mock_notify:
            await bridge.ask(task, question, timeout=60.0)

        mock_notify.assert_called_once()
        call_args = mock_notify.call_args[0]
        assert call_args[1] == "hitl_request"  # channel name
        payload = call_args[2]
        assert payload["agent_id"] == "requirements_analyst"
        assert payload["prompt"] == "Should we include mobile?"

    @pytest.mark.asyncio
    async def test_ask_uses_default_timeout_when_zero(self, bridge, task, question, waiter, mock_pool):
        waiter.wait_for = AsyncMock(return_value={"response": "y"})

        with patch("services.hitl_bridge.pg_notify", new_callable=AsyncMock), \
             patch("services.hitl_bridge.settings") as mock_settings:
            mock_settings.hitl_question_timeout = 900
            await bridge.ask(task, question, timeout=0)

        # waiter.wait_for should have been called with timeout=900.0
        call_kwargs = waiter.wait_for.call_args
        assert call_kwargs[1]["timeout"] == 900.0 or call_kwargs[0][1] == 900.0

    @pytest.mark.asyncio
    async def test_ask_timeout_propagates(self, bridge, task, question, waiter, mock_pool):
        waiter.wait_for = AsyncMock(side_effect=asyncio.TimeoutError())

        with patch("services.hitl_bridge.pg_notify", new_callable=AsyncMock):
            with pytest.raises(asyncio.TimeoutError):
                await bridge.ask(task, question, timeout=1.0)

    @pytest.mark.asyncio
    async def test_ask_empty_response(self, bridge, task, question, waiter, mock_pool):
        waiter.wait_for = AsyncMock(return_value={"response": "", "reviewer": "user"})

        with patch("services.hitl_bridge.pg_notify", new_callable=AsyncMock):
            result = await bridge.ask(task, question, timeout=60.0)

        assert result == ""

    @pytest.mark.asyncio
    async def test_ask_missing_response_key(self, bridge, task, question, waiter, mock_pool):
        waiter.wait_for = AsyncMock(return_value={"reviewer": "user"})

        with patch("services.hitl_bridge.pg_notify", new_callable=AsyncMock):
            result = await bridge.ask(task, question, timeout=60.0)

        assert result == ""


# ── HitlResponseWaiter ───────────────────────────────


class TestHitlResponseWaiter:
    @pytest.mark.asyncio
    async def test_wait_for_resolves_on_response(self):
        w = HitlResponseWaiter()

        async def respond_later():
            await asyncio.sleep(0.05)
            w.handle_response("hitl_response", {
                "request_id": "req-1",
                "response": "approved",
                "reviewer": "admin",
            })

        task = asyncio.create_task(respond_later())
        result = await w.wait_for("req-1", timeout=5.0)
        assert result["response"] == "approved"
        await task

    @pytest.mark.asyncio
    async def test_wait_for_timeout(self):
        w = HitlResponseWaiter()
        with pytest.raises(asyncio.TimeoutError):
            await w.wait_for("req-never", timeout=0.1)

    def test_handle_response_ignores_non_dict(self):
        w = HitlResponseWaiter()
        # Should not raise
        w.handle_response("ch", "not a dict")
        w.handle_response("ch", 42)
        w.handle_response("ch", None)

    def test_handle_response_ignores_unknown_request_id(self):
        w = HitlResponseWaiter()
        # No waiter registered, should not raise
        w.handle_response("ch", {"request_id": "unknown", "response": "x"})

    @pytest.mark.asyncio
    async def test_waiter_cleanup_after_resolve(self):
        w = HitlResponseWaiter()

        async def respond():
            await asyncio.sleep(0.01)
            w.handle_response("ch", {"request_id": "r1", "response": "ok"})

        asyncio.create_task(respond())
        await w.wait_for("r1", timeout=5.0)
        # After resolution, the waiter should be cleaned up
        assert "r1" not in w._waiters
