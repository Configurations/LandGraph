"""Inbox routes — notifications for the current user."""

from __future__ import annotations

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query

from core.security import TokenData, get_current_user
from schemas.inbox import NotificationResponse
from services import inbox_service

log = structlog.get_logger(__name__)

router = APIRouter(prefix="/api/pm/inbox", tags=["pm-inbox"])


@router.get("", response_model=list[NotificationResponse])
async def list_notifications(
    limit: int = Query(100, ge=1, le=500),
    user: TokenData = Depends(get_current_user),
) -> list[NotificationResponse]:
    """List notifications for the current user."""
    return await inbox_service.list_notifications(user.email, limit)


@router.put("/read-all")
async def mark_all_read(
    user: TokenData = Depends(get_current_user),
) -> dict:
    """Mark all notifications as read."""
    count = await inbox_service.mark_all_read(user.email)
    return {"ok": True, "count": count}


@router.get("/count")
async def unread_count(
    user: TokenData = Depends(get_current_user),
) -> dict:
    """Get unread notification count."""
    count = await inbox_service.get_unread_count(user.email)
    return {"count": count}


@router.put("/{notif_id}/read")
async def mark_read(
    notif_id: int,
    user: TokenData = Depends(get_current_user),
) -> dict:
    """Mark a single notification as read."""
    ok = await inbox_service.mark_read(notif_id, user.email)
    if not ok:
        raise HTTPException(status_code=404, detail="notification.not_found")
    return {"ok": True}
