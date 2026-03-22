"""Relation-related Pydantic v2 schemas."""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel


class RelationCreate(BaseModel):
    """Create a relation from a source issue to a target."""

    type: str
    target_issue_id: str
    reason: str = ""


class RelationBulkCreate(BaseModel):
    """Bulk-create relations."""

    relations: list[RelationCreate]
