"""Chat service — conversation history with agents via gateway invoke."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Optional

import httpx
import structlog

from core.config import settings
from core.database import execute, fetch_all, fetch_one
from schemas.chat import ChatMessageResponse

log = structlog.get_logger(__name__)

_GATEWAY_TIMEOUT = 120.0

# Shared directory for loading project prompts
_SHARED_DIR = Path(os.environ.get("SHARED_DIR", "/app/Shared"))
_PROJECTS_DIR = _SHARED_DIR / "Projects"


async def get_history(
    team_id: str,
    agent_id: str,
    limit: int = 200,
) -> list[ChatMessageResponse]:
    """Fetch chat history for a team/agent pair, chronological order."""
    rows = await fetch_all(
        """
        SELECT id, team_id, agent_id, thread_id, sender, content, created_at
        FROM project.hitl_chat_messages
        WHERE team_id = $1 AND agent_id = $2
        ORDER BY created_at DESC
        LIMIT $3
        """,
        team_id, agent_id, limit,
    )
    # Reverse to chronological
    rows = list(reversed(rows))
    return [
        ChatMessageResponse(
            id=r["id"],
            team_id=r["team_id"],
            agent_id=r["agent_id"],
            thread_id=r["thread_id"],
            sender=r["sender"],
            content=r["content"],
            created_at=r["created_at"],
        )
        for r in rows
    ]


async def send_message(
    team_id: str,
    agent_id: str,
    user_email: str,
    content: str,
    project_id: str = "",
    chat_id: str = "",
) -> ChatMessageResponse:
    """Send a message to an agent and return the agent's response."""
    thread_id = f"hitl-chat-{team_id}-{agent_id}"
    if project_id and chat_id:
        thread_id = f"hitl-chat-{team_id}-{agent_id}-{project_id}-{chat_id}"

    log.info(
        "chat_send_message",
        team_id=team_id,
        agent_id=agent_id,
        thread_id=thread_id,
        user=user_email,
        project_id=project_id or None,
        chat_id=chat_id or None,
    )

    # Load agent prompt if project/chat context is set
    system_prompt = ""
    if project_id and chat_id:
        system_prompt = _load_agent_prompt(project_id, chat_id, agent_id)

    # Insert user message
    await execute(
        """
        INSERT INTO project.hitl_chat_messages
            (team_id, agent_id, thread_id, sender, content)
        VALUES ($1, $2, $3, $4, $5)
        """,
        team_id, agent_id, thread_id, user_email, content,
    )

    # Call gateway
    agent_content = await _invoke_agent(team_id, agent_id, thread_id, content, system_prompt=system_prompt)

    # Insert agent response
    row = await fetch_one(
        """
        INSERT INTO project.hitl_chat_messages
            (team_id, agent_id, thread_id, sender, content)
        VALUES ($1, $2, $3, $4, $5)
        RETURNING id, team_id, agent_id, thread_id, sender, content, created_at
        """,
        team_id, agent_id, thread_id, agent_id, agent_content,
    )
    return ChatMessageResponse(
        id=row["id"],
        team_id=row["team_id"],
        agent_id=row["agent_id"],
        thread_id=row["thread_id"],
        sender=row["sender"],
        content=row["content"],
        created_at=row["created_at"],
    )


def _load_agent_prompt(project_id: str, chat_id: str, agent_id: str) -> str:
    """Load the generated agent prompt from the project directory."""
    project_dir = _PROJECTS_DIR / project_id
    if not project_dir.exists():
        log.warning("chat_project_not_found", project_id=project_id)
        return ""
    # Read project.json to find chat config
    pj_file = project_dir / "project.json"
    if not pj_file.exists():
        return ""
    try:
        pj = json.loads(pj_file.read_text(encoding="utf-8"))
    except Exception:
        return ""
    chats = pj.get("chats", [])
    chat = next((c for c in chats if c.get("id") == chat_id), None)
    if not chat:
        return ""
    agent_prompts = chat.get("agent_prompts", {})
    prompt_file = agent_prompts.get(agent_id, "")
    if not prompt_file:
        return ""
    prompt_path = project_dir / prompt_file
    if not prompt_path.exists():
        log.warning("chat_agent_prompt_not_found", path=str(prompt_path))
        return ""
    return prompt_path.read_text(encoding="utf-8")


async def _invoke_agent(
    team_id: str,
    agent_id: str,
    thread_id: str,
    message: str,
    system_prompt: str = "",
) -> str:
    """POST to the gateway /invoke endpoint. Returns agent response text."""
    config_key = "langgraph_api_url" if settings.langgraph_api_url else "dispatcher_url"
    url = settings.langgraph_api_url or settings.dispatcher_url
    if not url:
        log.error("chat_invoke_no_url", agent_id=agent_id)
        return "[error: no gateway URL configured]"

    invoke_url = f"{url.rstrip('/')}/invoke"
    payload = {
        "messages": [{"role": "user", "content": message}],
        "team_id": team_id,
        "thread_id": thread_id,
        "direct_agent": agent_id,
    }
    if system_prompt:
        payload["system_prompt"] = system_prompt

    log.info(
        "chat_invoke_agent",
        config_key=config_key,
        url=invoke_url,
        agent_id=agent_id,
        team_id=team_id,
        thread_id=thread_id,
        has_system_prompt=bool(system_prompt),
    )

    try:
        async with httpx.AsyncClient(timeout=_GATEWAY_TIMEOUT) as client:
            resp = await client.post(invoke_url, json=payload)
            resp.raise_for_status()
            data = resp.json()
            log.info(
                "chat_invoke_ok",
                agent_id=agent_id,
                status=resp.status_code,
                response_keys=list(data.keys()),
            )
            return data.get("output", data.get("response", data.get("content", "")))
    except httpx.HTTPStatusError as exc:
        status = exc.response.status_code
        log.error("chat_invoke_http_error", status=status, agent_id=agent_id)
        return f"[error: gateway returned {status}]"
    except Exception as exc:
        log.error("chat_invoke_error", error=str(exc), agent_id=agent_id)
        return f"[error: {exc}]"


async def clear_chat(team_id: str, agent_id: str) -> int:
    """Delete all messages for a team/agent chat. Returns count deleted."""
    thread_id = f"hitl-chat-{team_id}-{agent_id}"
    result = await execute(
        "DELETE FROM project.hitl_chat_messages WHERE thread_id = $1",
        thread_id,
    )
    # result is like "DELETE 42"
    try:
        count = int(result.split()[-1])
    except (ValueError, IndexError):
        count = 0
    log.info("chat_cleared", team_id=team_id, agent_id=agent_id, count=count)
    return count
