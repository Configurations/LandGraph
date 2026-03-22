"""RAG-related Pydantic v2 schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel


class RagSearchRequest(BaseModel):
    """RAG similarity search request."""

    project_slug: str
    query: str
    top_k: int = 5


class RagSearchResult(BaseModel):
    """Single RAG search result."""

    content: str
    filename: str
    chunk_index: int
    score: float
    metadata: dict = {}


class RagSearchResponse(BaseModel):
    """RAG search response with results list."""

    results: list[RagSearchResult]


class ConversationMessage(BaseModel):
    """A message in a project analysis conversation."""

    id: int
    project_slug: str
    task_id: Optional[UUID] = None
    sender: str
    content: str
    created_at: datetime


class UploadResponse(BaseModel):
    """Response after a file upload + indexing."""

    filename: str
    size: int
    content_type: str
    chunks_indexed: int
