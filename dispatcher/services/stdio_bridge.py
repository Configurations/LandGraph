"""Stdio bridge: read events from container stdout, write tasks to stdin."""

from __future__ import annotations

import json
import logging
from typing import Any, AsyncIterator

from models.task import (
    ArtifactEvent,
    EventType,
    ProgressEvent,
    QuestionEvent,
    ResultEvent,
    TaskEvent,
)

log = logging.getLogger(__name__)


async def write_task_json(ws: Any, task_dict: dict[str, Any]) -> None:
    """Write a single-line JSON task to the container stdin websocket."""
    line = json.dumps(task_dict, ensure_ascii=False) + "\n"
    await ws.send_bytes(line.encode("utf-8"))
    log.debug("Wrote task to stdin", extra={"task_id": task_dict.get("task_id", "?")})


async def write_answer_json(ws: Any, request_id: str, response: str) -> None:
    """Write a HITL answer to the container stdin."""
    payload = {"type": "answer", "request_id": request_id, "response": response}
    line = json.dumps(payload, ensure_ascii=False) + "\n"
    await ws.send_bytes(line.encode("utf-8"))
    log.debug("Wrote answer to stdin", extra={"request_id": request_id})


def parse_event_line(line: str) -> TaskEvent | None:
    """Parse a single stdout line into a typed TaskEvent. Returns None if invalid."""
    line = line.strip()
    if not line:
        return None
    try:
        obj = json.loads(line)
    except json.JSONDecodeError:
        log.warning("Non-JSON line from container stdout: %s", line[:200])
        return None

    task_id = obj.get("task_id", "")
    event_type = obj.get("type", "")
    data = obj.get("data")

    if event_type == EventType.PROGRESS:
        return ProgressEvent(task_id=task_id, data=str(data) if data is not None else "")

    if event_type == EventType.ARTIFACT:
        if not isinstance(data, dict):
            log.warning("Artifact event with non-dict data: %s", line[:200])
            return None
        return ArtifactEvent(
            task_id=task_id,
            key=data.get("key", ""),
            content=data.get("content", ""),
            deliverable_type=data.get("deliverable_type", ""),
        )

    if event_type == EventType.QUESTION:
        if not isinstance(data, dict):
            log.warning("Question event with non-dict data: %s", line[:200])
            return None
        return QuestionEvent(
            task_id=task_id,
            prompt=data.get("prompt", ""),
            context=data.get("context", {}),
        )

    if event_type == EventType.RESULT:
        if not isinstance(data, dict):
            log.warning("Result event with non-dict data: %s", line[:200])
            return None
        return ResultEvent(
            task_id=task_id,
            status=data.get("status", "failure"),
            exit_code=data.get("exit_code", -1),
            cost_usd=float(data.get("cost_usd", 0.0)),
        )

    log.warning("Unknown event type '%s': %s", event_type, line[:200])
    return None


async def read_events(stdout_lines: AsyncIterator[bytes]) -> AsyncIterator[TaskEvent]:
    """Read stdout line by line, parse and yield typed events."""
    async for raw in stdout_lines:
        text = raw.decode("utf-8", errors="replace") if isinstance(raw, bytes) else raw
        for line in text.splitlines():
            event = parse_event_line(line)
            if event is not None:
                yield event
