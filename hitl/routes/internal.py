"""Internal routes — no auth, network-only access."""

from __future__ import annotations

from fastapi import APIRouter

from schemas.rag import RagSearchRequest, RagSearchResponse
from services import rag_service

router = APIRouter(prefix="/api/internal", tags=["internal"])


@router.post("/rag/search", response_model=RagSearchResponse)
async def internal_rag_search(req: RagSearchRequest) -> RagSearchResponse:
    """RAG search endpoint for internal services (no auth)."""
    results = await rag_service.search(
        req.project_slug, req.query, req.top_k,
    )
    return RagSearchResponse(results=results)
