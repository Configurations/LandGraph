"""Relation routes — CRUD for issue relations."""

from __future__ import annotations

import structlog
from fastapi import APIRouter, Depends, HTTPException

from core.security import TokenData, get_current_user
from schemas.issue import RelationResponse
from schemas.relation import RelationBulkCreate, RelationCreate
from services import relation_service

log = structlog.get_logger(__name__)

router = APIRouter(prefix="/api/pm", tags=["pm-relations"])


@router.get("/issues/{issue_id}/relations", response_model=list[RelationResponse])
async def list_relations(
    issue_id: str,
    user: TokenData = Depends(get_current_user),
) -> list[RelationResponse]:
    """List all relations for an issue."""
    return await relation_service.list_relations(issue_id)


@router.post(
    "/issues/{issue_id}/relations",
    response_model=RelationResponse,
    status_code=201,
)
async def create_relation(
    issue_id: str,
    body: RelationCreate,
    user: TokenData = Depends(get_current_user),
) -> RelationResponse:
    """Create a relation from this issue to another."""
    try:
        return await relation_service.create_relation(issue_id, body, user.email)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.delete("/relations/{relation_id}", status_code=204)
async def delete_relation(
    relation_id: int,
    user: TokenData = Depends(get_current_user),
) -> None:
    """Delete a relation."""
    ok = await relation_service.delete_relation(relation_id, user.email)
    if not ok:
        raise HTTPException(status_code=404, detail="relation.not_found")


@router.post(
    "/issues/{issue_id}/relations/bulk",
    response_model=list[RelationResponse],
    status_code=201,
)
async def bulk_create_relations(
    issue_id: str,
    body: RelationBulkCreate,
    user: TokenData = Depends(get_current_user),
) -> list[RelationResponse]:
    """Bulk-create relations from this issue."""
    return await relation_service.bulk_create(issue_id, body.relations, user.email)
