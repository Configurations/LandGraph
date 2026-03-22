"""Tests for services.stdio_bridge — event parsing and stdin writing."""

from __future__ import annotations

import json
import pytest
from unittest.mock import AsyncMock

from models.task import (
    ArtifactEvent,
    EventType,
    ProgressEvent,
    QuestionEvent,
    ResultEvent,
)
from services.stdio_bridge import parse_event_line, write_task_json, write_answer_json, read_events


# ── parse_event_line ─────────────────────────────────


class TestParseEventLine:
    """Test parse_event_line with various inputs."""

    def test_progress_event(self):
        line = json.dumps({"task_id": "t1", "type": "progress", "data": "Step 3/10"})
        event = parse_event_line(line)
        assert isinstance(event, ProgressEvent)
        assert event.task_id == "t1"
        assert event.data == "Step 3/10"

    def test_progress_event_null_data(self):
        line = json.dumps({"task_id": "t1", "type": "progress", "data": None})
        event = parse_event_line(line)
        assert isinstance(event, ProgressEvent)
        assert event.data == ""

    def test_artifact_event(self):
        line = json.dumps({
            "task_id": "t2",
            "type": "artifact",
            "data": {"key": "prd", "content": "# PRD\nContent here", "deliverable_type": "document"},
        })
        event = parse_event_line(line)
        assert isinstance(event, ArtifactEvent)
        assert event.task_id == "t2"
        assert event.key == "prd"
        assert event.content == "# PRD\nContent here"
        assert event.deliverable_type == "document"

    def test_artifact_event_non_dict_data_returns_none(self):
        line = json.dumps({"task_id": "t2", "type": "artifact", "data": "bad"})
        assert parse_event_line(line) is None

    def test_question_event(self):
        line = json.dumps({
            "task_id": "t3",
            "type": "question",
            "data": {"prompt": "Confirm scope?", "context": {"phase": "discovery"}},
        })
        event = parse_event_line(line)
        assert isinstance(event, QuestionEvent)
        assert event.prompt == "Confirm scope?"
        assert event.context == {"phase": "discovery"}

    def test_question_event_non_dict_data_returns_none(self):
        line = json.dumps({"task_id": "t3", "type": "question", "data": 42})
        assert parse_event_line(line) is None

    def test_result_event_success(self):
        line = json.dumps({
            "task_id": "t4",
            "type": "result",
            "data": {"status": "success", "exit_code": 0, "cost_usd": 0.05},
        })
        event = parse_event_line(line)
        assert isinstance(event, ResultEvent)
        assert event.status == "success"
        assert event.exit_code == 0
        assert event.cost_usd == pytest.approx(0.05)

    def test_result_event_failure_defaults(self):
        line = json.dumps({"task_id": "t4", "type": "result", "data": {}})
        event = parse_event_line(line)
        assert isinstance(event, ResultEvent)
        assert event.status == "failure"
        assert event.exit_code == -1
        assert event.cost_usd == 0.0

    def test_result_event_non_dict_data_returns_none(self):
        line = json.dumps({"task_id": "t4", "type": "result", "data": "oops"})
        assert parse_event_line(line) is None

    def test_empty_line_returns_none(self):
        assert parse_event_line("") is None
        assert parse_event_line("   ") is None

    def test_invalid_json_returns_none(self):
        assert parse_event_line("not json at all") is None
        assert parse_event_line("{broken") is None

    def test_unknown_event_type_returns_none(self):
        line = json.dumps({"task_id": "t5", "type": "unknown_type", "data": {}})
        assert parse_event_line(line) is None

    def test_missing_type_returns_none(self):
        line = json.dumps({"task_id": "t5", "data": "hello"})
        assert parse_event_line(line) is None

    def test_whitespace_stripped(self):
        line = "  " + json.dumps({"task_id": "t1", "type": "progress", "data": "ok"}) + "  \n"
        event = parse_event_line(line)
        assert isinstance(event, ProgressEvent)


# ── write_task_json ──────────────────────────────────


class TestWriteTaskJson:
    @pytest.mark.asyncio
    async def test_sends_json_newline_as_bytes(self):
        ws = AsyncMock()
        task_dict = {"task_id": "abc", "agent_id": "dev"}
        await write_task_json(ws, task_dict)

        ws.send_bytes.assert_called_once()
        sent = ws.send_bytes.call_args[0][0]
        assert isinstance(sent, bytes)
        decoded = sent.decode("utf-8")
        assert decoded.endswith("\n")
        parsed = json.loads(decoded.strip())
        assert parsed["task_id"] == "abc"


# ── write_answer_json ────────────────────────────────


class TestWriteAnswerJson:
    @pytest.mark.asyncio
    async def test_sends_answer_payload(self):
        ws = AsyncMock()
        await write_answer_json(ws, "req-123", "Yes, approved")

        ws.send_bytes.assert_called_once()
        sent = ws.send_bytes.call_args[0][0]
        parsed = json.loads(sent.decode("utf-8").strip())
        assert parsed["type"] == "answer"
        assert parsed["request_id"] == "req-123"
        assert parsed["response"] == "Yes, approved"


# ── read_events ──────────────────────────────────────


class TestReadEvents:
    @pytest.mark.asyncio
    async def test_yields_valid_events_skips_invalid(self):
        lines = [
            json.dumps({"task_id": "t1", "type": "progress", "data": "step1"}).encode(),
            b"not json\n",
            json.dumps({"task_id": "t1", "type": "result", "data": {"status": "success", "exit_code": 0, "cost_usd": 0}}).encode(),
        ]

        async def mock_lines():
            for line in lines:
                yield line

        events = []
        async for ev in read_events(mock_lines()):
            events.append(ev)

        assert len(events) == 2
        assert isinstance(events[0], ProgressEvent)
        assert isinstance(events[1], ResultEvent)

    @pytest.mark.asyncio
    async def test_handles_multiline_in_single_chunk(self):
        chunk = (
            json.dumps({"task_id": "t1", "type": "progress", "data": "a"})
            + "\n"
            + json.dumps({"task_id": "t1", "type": "progress", "data": "b"})
        ).encode()

        async def mock_lines():
            yield chunk

        events = []
        async for ev in read_events(mock_lines()):
            events.append(ev)

        assert len(events) == 2
        assert events[0].data == "a"
        assert events[1].data == "b"
