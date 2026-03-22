"""Tests for routes/rag.py + routes/internal.py — upload, search, analysis."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient

from core.security import encode_token
from tests.conftest import SAMPLE_USER_ID, make_record

ADMIN_TOKEN = encode_token(str(SAMPLE_USER_ID), "admin@t.com", "admin", ["team1"])

NOW = datetime(2026, 3, 20, tzinfo=timezone.utc)


def _project_row(**overrides):
    defaults = dict(
        id=1, name="Proj", slug="proj", team_id="team1",
        language="fr", git_service="github", git_url="https://github.com",
        git_login="user", git_repo_name="user/repo",
        status="on-track", color="#6366f1",
        created_at=NOW, updated_at=NOW,
    )
    defaults.update(overrides)
    return make_record(**defaults)


AUTH = {"Authorization": f"Bearer {ADMIN_TOKEN}"}


# ── POST /api/projects/{slug}/upload ─────────────────────────

@pytest.mark.asyncio
async def test_upload_file_200(app_client: AsyncClient, mock_pool: AsyncMock):
    """POST upload returns filename, size, chunks_indexed."""
    mock_pool.fetchrow.return_value = _project_row()

    with (
        patch("services.upload_service.save_file", new_callable=AsyncMock, return_value=("/tmp/readme.md", 100)),
        patch("services.upload_service.extract_text", return_value="some text"),
        patch("services.rag_service.index_document", new_callable=AsyncMock, return_value=3),
    ):
        resp = await app_client.post(
            "/api/projects/proj/upload",
            files={"file": ("readme.md", b"# Hello", "text/markdown")},
            headers=AUTH,
        )

    assert resp.status_code == 200
    body = resp.json()
    assert body["filename"] == "readme.md"
    assert body["chunks_indexed"] == 3


# ── GET /api/projects/{slug}/uploads ─────────────────────────

@pytest.mark.asyncio
async def test_list_uploads(app_client: AsyncClient, mock_pool: AsyncMock):
    """GET uploads returns file metadata list."""
    mock_pool.fetchrow.return_value = _project_row()

    with patch("services.upload_service.list_uploads", new_callable=AsyncMock, return_value=[
        {"name": "a.md", "size": 100, "content_type": "text/markdown"},
    ]):
        resp = await app_client.get("/api/projects/proj/uploads", headers=AUTH)

    assert resp.status_code == 200
    assert len(resp.json()) == 1


# ── DELETE /api/projects/{slug}/uploads/{filename} ───────────

@pytest.mark.asyncio
async def test_delete_upload_200(app_client: AsyncClient, mock_pool: AsyncMock):
    """DELETE upload returns ok."""
    mock_pool.fetchrow.return_value = _project_row()

    with patch("services.upload_service.delete_upload", new_callable=AsyncMock, return_value=True):
        resp = await app_client.delete("/api/projects/proj/uploads/readme.md", headers=AUTH)

    assert resp.status_code == 200
    assert resp.json()["ok"] is True


# ── POST /api/projects/{slug}/search ─────────────────────────

@pytest.mark.asyncio
async def test_search_rag(app_client: AsyncClient, mock_pool: AsyncMock):
    """POST search returns RAG results."""
    mock_pool.fetchrow.return_value = _project_row()

    from schemas.rag import RagSearchResult
    fake_results = [
        RagSearchResult(content="hit", filename="a.md", chunk_index=0, score=0.9, metadata={}),
    ]

    with patch("services.rag_service.search", new_callable=AsyncMock, return_value=fake_results):
        resp = await app_client.post("/api/projects/proj/search", json={
            "project_slug": "proj", "query": "test", "top_k": 5,
        }, headers=AUTH)

    assert resp.status_code == 200
    assert len(resp.json()["results"]) == 1
    assert resp.json()["results"][0]["score"] == 0.9


# ── POST /api/projects/{slug}/analysis/start ─────────────────

@pytest.mark.asyncio
async def test_start_analysis_success(app_client: AsyncClient, mock_pool: AsyncMock):
    """POST analysis/start returns task_id on success."""
    mock_pool.fetchrow.return_value = _project_row()

    with patch("services.analysis_service.start_analysis", new_callable=AsyncMock, return_value={"task_id": "abc-123"}):
        resp = await app_client.post("/api/projects/proj/analysis/start", headers=AUTH)

    assert resp.status_code == 200
    assert resp.json()["task_id"] == "abc-123"


@pytest.mark.asyncio
async def test_start_analysis_dispatcher_error(app_client: AsyncClient, mock_pool: AsyncMock):
    """POST analysis/start returns error when dispatcher unavailable."""
    mock_pool.fetchrow.return_value = _project_row()

    with patch(
        "services.analysis_service.start_analysis",
        new_callable=AsyncMock,
        return_value={"error": "dispatcher_unavailable"},
    ):
        resp = await app_client.post("/api/projects/proj/analysis/start", headers=AUTH)

    assert resp.status_code == 200
    assert resp.json()["error"] == "dispatcher_unavailable"


# ── POST /api/internal/rag/search ────────────────────────────

@pytest.mark.asyncio
async def test_internal_rag_search_no_auth(app_client: AsyncClient, mock_pool: AsyncMock):
    """Internal RAG search works without auth token."""
    from schemas.rag import RagSearchResult
    fake = [RagSearchResult(content="c", filename="f", chunk_index=0, score=0.8, metadata={})]

    with patch("services.rag_service.search", new_callable=AsyncMock, return_value=fake):
        resp = await app_client.post("/api/internal/rag/search", json={
            "project_slug": "proj", "query": "q", "top_k": 3,
        })

    assert resp.status_code == 200
    assert len(resp.json()["results"]) == 1
