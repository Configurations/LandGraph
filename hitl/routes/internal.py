"""Internal routes — no auth, network-only access."""

from __future__ import annotations

from fastapi import APIRouter

from schemas.rag import RagIndexRequest, RagIndexResponse, RagSearchRequest, RagSearchResponse
from services import rag_service

router = APIRouter(prefix="/api/internal", tags=["internal"])


@router.post("/rag/search", response_model=RagSearchResponse)
async def internal_rag_search(req: RagSearchRequest) -> RagSearchResponse:
    """RAG search endpoint for internal services (no auth)."""
    results = await rag_service.search(
        req.project_slug, req.query, req.top_k,
    )
    return RagSearchResponse(results=results)


@router.post("/rag/index", response_model=RagIndexResponse)
async def internal_rag_index(req: RagIndexRequest) -> RagIndexResponse:
    """RAG index endpoint for internal services (no auth)."""
    filename = "orchestrator/{}/{}".format(req.source_type, req.source_agent)
    chunks = await rag_service.index_document(
        req.project_slug, filename, req.content, "text/plain",
    )
    return RagIndexResponse(chunks=chunks)
