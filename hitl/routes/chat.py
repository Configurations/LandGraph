"""Chat routes — conversation with agents."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from core.security import TokenData, get_current_user
from schemas.chat import ChatMessageResponse, SendMessageRequest
from services import chat_service

router = APIRouter(tags=["chat"])


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
