"""WebSocket route for real-time HITL notifications."""

from __future__ import annotations

import asyncio
import json

import structlog
from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect
from jose import JWTError

from core.security import decode_token
from core.websocket_manager import ws_manager

log = structlog.get_logger(__name__)

router = APIRouter(tags=["ws"])


def _handle_ws_message(websocket: WebSocket, raw: str) -> None:
    """Process incoming WS messages for watch/unwatch commands."""
    try:
        msg = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return

    msg_type = msg.get("type", "")
    if msg_type == "watch_chat":
        agent_id = msg.get("agent_id", "")
        if agent_id:
            ws_manager.watch_chat(websocket, agent_id)
    elif msg_type == "unwatch_chat":
        ws_manager.unwatch_chat(websocket)


@router.websocket("/api/teams/{team_id}/ws")
async def team_websocket(
    websocket: WebSocket,
    team_id: str,
    token: str = Query(...),
) -> None:
    """WebSocket endpoint for team-level real-time events."""
    # Authenticate via JWT query param
    try:
        payload = decode_token(token)
    except JWTError:
        await websocket.close(code=4001, reason="invalid_token")
        return

    role = payload.get("role", "")
    teams = payload.get("teams", [])
    email = payload.get("email", "")

    # Check team access
    if role != "admin" and team_id not in teams:
        await websocket.close(code=4003, reason="team_access_denied")
        return

    await websocket.accept()
    await ws_manager.connect(team_id, websocket, user_email=email)
    log.info("ws_connected", team_id=team_id, email=email)

    try:
        while True:
            # Receive loop — handle watch/unwatch + keep alive
            try:
                raw = await asyncio.wait_for(
                    websocket.receive_text(), timeout=45.0,
                )
                _handle_ws_message(websocket, raw)
            except asyncio.TimeoutError:
                # Send ping to keep alive
                try:
                    await websocket.send_json({"type": "ping"})
                except Exception:
                    break
    except WebSocketDisconnect:
        pass
    except Exception as exc:
        log.debug("ws_error", team_id=team_id, error=str(exc))
    finally:
        await ws_manager.disconnect(team_id, websocket)
        log.info("ws_disconnected", team_id=team_id, email=email)
