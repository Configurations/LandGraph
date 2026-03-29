"""Chat routes — conversation with agents."""

from __future__ import annotations

import json
import os
from pathlib import Path

from fastapi import APIRouter, Depends

from core.security import TokenData, get_current_user
from schemas.chat import ChatMessageResponse, SendMessageRequest
from services import chat_service

router = APIRouter(tags=["chat"])

_SHARED_DIR = Path(os.environ.get("SHARED_DIR", "/app/Shared"))
_PROJECTS_DIR = _SHARED_DIR / "Projects"


@router.get(
    "/api/teams/{team_id}/agents/{agent_id}/chat",
    response_model=list[ChatMessageResponse],
)
async def get_chat_history(
    team_id: str,
    agent_id: str,
    user: TokenData = Depends(get_current_user),
) -> list[ChatMessageResponse]:
    """Get chat history with an agent."""
    return await chat_service.get_history(team_id, agent_id)


@router.post(
    "/api/teams/{team_id}/agents/{agent_id}/chat",
    response_model=ChatMessageResponse,
)
async def send_message(
    team_id: str,
    agent_id: str,
    body: SendMessageRequest,
    user: TokenData = Depends(get_current_user),
) -> ChatMessageResponse:
    """Send a message to an agent and get the response."""
    return await chat_service.send_message(
        team_id, agent_id, user.email, body.message,
        project_id=body.project_id, chat_id=body.chat_id,
    )


@router.delete("/api/teams/{team_id}/agents/{agent_id}/chat")
async def clear_chat(
    team_id: str,
    agent_id: str,
    user: TokenData = Depends(get_current_user),
) -> dict:
    """Clear chat history with an agent."""
    count = await chat_service.clear_chat(team_id, agent_id)
    return {"ok": True, "deleted": count}


@router.get("/api/chat-contexts")
async def list_chat_contexts(
    user: TokenData = Depends(get_current_user),
) -> list[dict]:
    """List all projects with their chat configurations for the chat context selector."""
    results = []
    if not _PROJECTS_DIR.exists():
        return results
    for pdir in sorted(_PROJECTS_DIR.iterdir()):
        if not pdir.is_dir():
            continue
        pj_file = pdir / "project.json"
        if not pj_file.exists():
            continue
        try:
            pj = json.loads(pj_file.read_text(encoding="utf-8"))
        except Exception:
            continue
        chats = pj.get("chats", [])
        if not chats:
            continue
        results.append({
            "project_id": pdir.name,
            "project_name": pj.get("name", pdir.name),
            "chats": [
                {
                    "id": c.get("id", ""),
                    "type": c.get("type", ""),
                    "agents": c.get("agents", []),
                    "agent_prompts": c.get("agent_prompts", {}),
                }
                for c in chats
            ],
        })
    return results
