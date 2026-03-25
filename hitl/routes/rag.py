"""RAG routes — upload, search, analysis."""

from __future__ import annotations

import mimetypes
import os
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, UploadFile

from core.security import TokenData, get_current_user
from schemas.rag import (
    AnalysisFreeMessageRequest,
    AnalysisMessage,
    AnalysisReplyRequest,
    ConversationMessage,
    GitCloneRequest,
    GitCloneResponse,
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
    """Upload a file, extract text, and index in RAG.

    Archives (ZIP, TAR) are auto-extracted into a subdirectory and each
    extracted file is individually indexed.
    """
    await _require_project(slug, user)

    content_bytes = await file.read()
    filename = file.filename or "untitled"
    filepath_or_dir, size, extracted_files = await upload_service.save_file(
        slug, filename, content_bytes,
    )

    chunks_indexed = 0

    if extracted_files:
        # Archive was extracted — index each file
        for fpath in extracted_files:
            text = upload_service.extract_text(fpath)
            if text.strip():
                rel_name = os.path.relpath(fpath, os.path.dirname(filepath_or_dir))
                ct, _ = mimetypes.guess_type(fpath)
                chunks_indexed += await rag_service.index_document(
                    slug, rel_name, text, ct or "text/plain",
                )
    else:
        # Single file
        text = upload_service.extract_text(filepath_or_dir)
        if text.strip():
            ct, _ = mimetypes.guess_type(filename)
            chunks_indexed = await rag_service.index_document(
                slug, filename, text, ct or "text/plain",
            )

    return UploadResponse(
        filename=filename,
        size=size,
        content_type=file.content_type or "application/octet-stream",
        chunks_indexed=chunks_indexed,
        files_extracted=len(extracted_files),
    )


@router.post("/{slug}/upload-git", response_model=GitCloneResponse)
async def upload_git(
    slug: str,
    req: GitCloneRequest,
    user: TokenData = Depends(get_current_user),
) -> GitCloneResponse:
    """Clone a git repo into the project uploads directory and index files."""
    project = await project_service.get_project(slug)
    if not project:
        raise HTTPException(status_code=404, detail="project.not_found")
    _check_project_access(user, project.team_id)

    # Resolve credentials
    service = req.service or (project.git_service if req.use_project_creds else "other")
    url = req.url or (project.git_url if req.use_project_creds else "")
    login = req.login or (project.git_login if req.use_project_creds else "")
    token = req.token
    if not token and req.use_project_creds:
        # Read token from DB (git_token_env stores the actual token at creation)
        from core.database import fetch_one
        row = await fetch_one(
            "SELECT git_token_env FROM project.pm_projects WHERE slug = $1", slug,
        )
        token = row["git_token_env"] if row else ""

    try:
        dest_dir, files = await upload_service.clone_git_to_uploads(
            slug, req.repo_name, service, url, login, token,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    # Index extracted files
    chunks_indexed = 0
    for fpath in files:
        text = upload_service.extract_text(fpath)
        if text.strip():
            rel_name = os.path.relpath(fpath, os.path.dirname(dest_dir))
            ct, _ = mimetypes.guess_type(fpath)
            chunks_indexed += await rag_service.index_document(
                slug, rel_name, text, ct or "text/plain",
            )

    short_name = os.path.basename(dest_dir)
    return GitCloneResponse(
        directory=short_name,
        files_count=len(files),
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
    user: TokenData = Depends(get_current_user),
) -> dict:
    """Check analysis status with dispatcher sync."""
    await _require_project(slug, user)
    return await analysis_service.get_analysis_status(slug)


@router.get(
    "/{slug}/analysis/conversation",
    response_model=list[AnalysisMessage],
)
async def get_conversation(
    slug: str,
    user: TokenData = Depends(get_current_user),
) -> list[AnalysisMessage]:
    """Get the merged analysis conversation history."""
    await _require_project(slug, user)
    return await analysis_service.get_conversation(slug)


@router.post("/{slug}/analysis/reply")
async def reply_to_question(
    slug: str,
    body: AnalysisReplyRequest,
    user: TokenData = Depends(get_current_user),
) -> dict:
    """Reply to an agent question in the analysis conversation."""
    await _require_project(slug, user)
    try:
        return await analysis_service.reply_to_question(
            slug, body.request_id, body.response, user.email,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/{slug}/analysis/message")
async def send_free_message(
    slug: str,
    body: AnalysisFreeMessageRequest,
    user: TokenData = Depends(get_current_user),
) -> dict:
    """Send a free message — relaunches the agent with enriched context."""
    await _require_project(slug, user)
    try:
        return await analysis_service.send_free_message(
            slug, body.content, user.email,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
