"""RAG-related Pydantic v2 schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional
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


class AnalysisMessage(BaseModel):
    """A message in the unified analysis conversation."""

    id: str
    sender: Literal["agent", "user", "system"]
    type: Literal["progress", "question", "reply", "artifact", "result", "system"]
    content: str
    request_id: Optional[str] = None
    status: Optional[str] = None
    artifact_key: Optional[str] = None
    created_at: str


class AnalysisReplyRequest(BaseModel):
    """Reply to an agent question."""

    request_id: str
    response: str


class AnalysisFreeMessageRequest(BaseModel):
    """Free message to the agent (triggers relaunch)."""

    content: str


class UploadResponse(BaseModel):
    """Response after a file upload + indexing."""

    filename: str
    size: int
    content_type: str
    chunks_indexed: int
    files_extracted: int = 0


class GitCloneRequest(BaseModel):
    """Request to clone a git repo into project uploads."""

    repo_name: str
    service: str = ""
    url: str = ""
    login: str = ""
    token: str = ""
    use_project_creds: bool = True


class GitCloneResponse(BaseModel):
    """Response after cloning a git repo."""

    directory: str
    files_count: int
    chunks_indexed: int
