"""RAG routes — upload, search, analysis."""

from __future__ import annotations

import mimetypes
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, UploadFile

from core.security import TokenData, get_current_user
from schemas.rag import (
    ConversationMessage,
    RagSearchRequest,
    RagSearchResponse,
    UploadResponse,
)
from services import analysis_service, project_service, rag_service, upload_service

router = APIRouter(prefix="/api/projects", tags=["rag"])


def _check_project_access(user: TokenData, team_id: str) -> None:
    """Raise 403 if user has no access to the project team."""
    if user.role == "admin":
        return
    if team_id not in user.teams:
        raise HTTPException(status_code=403, detail="team.access_denied")


async def _require_project(slug: str, user: TokenData) -> None:
    """Validate project exists and user has access."""
    project = await project_service.get_project(slug)
    if not project:
        raise HTTPException(status_code=404, detail="project.not_found")
    _check_project_access(user, project.team_id)


@router.post("/{slug}/upload", response_model=UploadResponse)
async def upload_file(
    slug: str,
    file: UploadFile,
    user: TokenData = Depends(get_current_user),
) -> UploadResponse:
    """Upload a file, extract text, and index in RAG."""
    await _require_project(slug, user)

    content_bytes = await file.read()
    filename = file.filename or "untitled"
    filepath, size = await upload_service.save_file(slug, filename, content_bytes)

    text = upload_service.extract_text(filepath)
    chunks_indexed = 0
    if text.strip():
        ct, _ = mimetypes.guess_type(filename)
        content_type = ct or "text/plain"
        chunks_indexed = await rag_service.index_document(
            slug, filename, text, content_type,
        )

    return UploadResponse(
        filename=filename,
        size=size,
        content_type=file.content_type or "application/octet-stream",
        chunks_indexed=chunks_indexed,
    )


@router.get("/{slug}/uploads")
async def list_uploads(
    slug: str,
    user: TokenData = Depends(get_current_user),
) -> list[dict]:
    """List uploaded files for a project."""
    await _require_project(slug, user)
    return await upload_service.list_uploads(slug)


@router.delete("/{slug}/uploads/{filename}")
async def delete_upload(
    slug: str,
    filename: str,
    user: TokenData = Depends(get_current_user),
) -> dict:
    """Delete an uploaded file and its RAG index."""
    await _require_project(slug, user)
    await upload_service.delete_upload(slug, filename)
    return {"ok": True}


@router.post("/{slug}/search", response_model=RagSearchResponse)
async def search_rag(
    slug: str,
    req: RagSearchRequest,
    user: TokenData = Depends(get_current_user),
) -> RagSearchResponse:
    """Semantic search over project documents."""
    await _require_project(slug, user)
    results = await rag_service.search(slug, req.query, req.top_k)
    return RagSearchResponse(results=results)


@router.post("/{slug}/analysis/start")
async def start_analysis(
    slug: str,
    user: TokenData = Depends(get_current_user),
) -> dict:
    """Start an AI analysis of project documents."""
    project = await project_service.get_project(slug)
    if not project:
        raise HTTPException(status_code=404, detail="project.not_found")
    _check_project_access(user, project.team_id)
    return await analysis_service.start_analysis(slug, project.team_id)


@router.get("/{slug}/analysis/status")
async def analysis_status(
    slug: str,
    task_id: str,
    user: TokenData = Depends(get_current_user),
) -> dict:
    """Check analysis task status."""
    await _require_project(slug, user)
    return await analysis_service.get_analysis_status(task_id)


@router.get(
    "/{slug}/analysis/conversation",
    response_model=list[ConversationMessage],
)
async def get_conversation(
    slug: str,
    user: TokenData = Depends(get_current_user),
) -> list[ConversationMessage]:
    """Get the analysis conversation history."""
    await _require_project(slug, user)
    return await analysis_service.get_conversation(slug)
