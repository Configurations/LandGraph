"""Automation rules routes — CRUD, stats, confidence."""

from __future__ import annotations

from typing import Optional

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query

from core.security import TokenData, get_current_user
from schemas.automation import (
    AgentConfidenceResponse,
    AutomationRuleCreate,
    AutomationRuleResponse,
    AutomationStatsResponse,
)
from services import automation_service

log = structlog.get_logger(__name__)

router = APIRouter(prefix="/api/automation", tags=["automation"])


@router.get("/rules", response_model=list[AutomationRuleResponse])
async def list_rules(
    project_slug: Optional[str] = Query(None),
    user: TokenData = Depends(get_current_user),
) -> list[AutomationRuleResponse]:
    """List automation rules."""
    return await automation_service.list_rules(project_slug)


@router.post("/rules", response_model=AutomationRuleResponse, status_code=201)
async def create_rule(
    body: AutomationRuleCreate,
    user: TokenData = Depends(get_current_user),
) -> AutomationRuleResponse:
    """Create a new automation rule."""
    return await automation_service.create_rule(body)


@router.put("/rules/{rule_id}", response_model=AutomationRuleResponse)
async def update_rule(
    rule_id: int,
    body: AutomationRuleCreate,
    user: TokenData = Depends(get_current_user),
) -> AutomationRuleResponse:
    """Update an existing automation rule."""
    rule = await automation_service.update_rule(rule_id, body)
    if rule is None:
        raise HTTPException(status_code=404, detail="automation.rule_not_found")
    return rule


@router.delete("/rules/{rule_id}")
async def delete_rule(
    rule_id: int,
    user: TokenData = Depends(get_current_user),
) -> dict:
    """Delete an automation rule."""
    ok = await automation_service.delete_rule(rule_id)
    if not ok:
        raise HTTPException(status_code=404, detail="automation.rule_not_found")
    return {"ok": True}


@router.get("/stats", response_model=AutomationStatsResponse)
async def get_stats(
    project_slug: str = Query(...),
    user: TokenData = Depends(get_current_user),
) -> AutomationStatsResponse:
    """Get automation statistics for a project."""
    return await automation_service.get_automation_stats(project_slug)


@router.get("/agent-confidence/{agent_id}", response_model=AgentConfidenceResponse)
async def get_agent_confidence(
    agent_id: str,
    deliverable_type: Optional[str] = Query(None),
    user: TokenData = Depends(get_current_user),
) -> AgentConfidenceResponse:
    """Get confidence score for an agent."""
    return await automation_service.get_agent_confidence(agent_id, deliverable_type)
