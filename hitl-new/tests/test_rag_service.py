"""Tests for services/rag_service.py — chunking, indexing, search."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from tests.conftest import make_record


# ── chunk_text ───────────────────────────────────────────────

def test_chunk_text_splits_by_paragraphs():
    """chunk_text splits on double newlines."""
    from services.rag_service import chunk_text

    text = "First paragraph.\n\nSecond paragraph.\n\nThird paragraph."
    chunks = chunk_text(text, max_tokens=50, overlap=0)
    assert len(chunks) >= 1
    assert "First paragraph." in chunks[0]


def test_chunk_text_merges_small_chunks():
    """Tiny chunks (< 200 tokens) get merged with previous."""
    from services.rag_service import chunk_text

    # Build text with many tiny paragraphs
    paragraphs = ["Word " * 5 for _ in range(10)]
    text = "\n\n".join(paragraphs)
    chunks = chunk_text(text, max_tokens=2000, overlap=0)
    # All should merge into 1 chunk since total is well under 2000 tokens
    assert len(chunks) == 1


def test_chunk_text_splits_large_block():
    """A single paragraph exceeding max_tokens gets split by lines."""
    from services.rag_service import chunk_text

    # Create a large single paragraph (no double newlines)
    # Each line ~260 tokens so split chunks exceed the 200-token merge threshold
    lines = ["Line " + str(i) + " " + "word " * 200 for i in range(10)]
    text = "\n".join(lines)
    chunks = chunk_text(text, max_tokens=300, overlap=0)
    assert len(chunks) > 1


def test_chunk_text_overlap():
    """Chunks have overlap from the tail of the previous chunk."""
    from services.rag_service import chunk_text

    # Build paragraphs that force splitting
    p1 = "Alpha " * 200
    p2 = "Beta " * 200
    p3 = "Gamma " * 200
    text = f"{p1}\n\n{p2}\n\n{p3}"
    chunks = chunk_text(text, max_tokens=300, overlap=50)
    # With overlap, later chunks may contain tail of previous
    assert len(chunks) >= 2


def test_chunk_text_empty():
    """Empty text returns no chunks."""
    from services.rag_service import chunk_text
    assert chunk_text("") == []
    assert chunk_text("   ") == []


# ── index_document ───────────────────────────────────────────

FAKE_VECTOR = [0.1, 0.2, 0.3]


@pytest.mark.asyncio
async def test_index_document_chunks_and_inserts():
    """index_document chunks text, calls get_embedding, inserts per chunk."""
    mock_pool = AsyncMock()
    mock_pool.execute = AsyncMock()

    with (
        patch("services.rag_service.execute", new_callable=AsyncMock),
        patch("services.rag_service.get_pool", return_value=mock_pool),
        patch("services.rag_service.get_embedding", new_callable=AsyncMock, return_value=FAKE_VECTOR),
        patch("services.rag_service.chunk_text", return_value=["chunk1", "chunk2"]),
    ):
        from services.rag_service import index_document
        count = await index_document("proj", "readme.md", "some text", "text/markdown")

    assert count == 2
    assert mock_pool.execute.call_count == 2


@pytest.mark.asyncio
async def test_index_document_empty_content():
    """index_document returns 0 when text produces no chunks."""
    with (
        patch("services.rag_service.execute", new_callable=AsyncMock),
        patch("services.rag_service.get_pool", return_value=AsyncMock()),
        patch("services.rag_service.chunk_text", return_value=[]),
    ):
        from services.rag_service import index_document
        count = await index_document("proj", "empty.md", "", "text/markdown")

    assert count == 0


@pytest.mark.asyncio
async def test_index_document_embedding_failure_skips_chunk():
    """If get_embedding fails for a chunk, that chunk is skipped."""
    mock_pool = AsyncMock()
    mock_pool.execute = AsyncMock()

    call_count = 0

    async def flaky_embed(text):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise RuntimeError("API down")
        return FAKE_VECTOR

    with (
        patch("services.rag_service.execute", new_callable=AsyncMock),
        patch("services.rag_service.get_pool", return_value=mock_pool),
        patch("services.rag_service.get_embedding", side_effect=flaky_embed),
        patch("services.rag_service.chunk_text", return_value=["fail", "ok"]),
    ):
        from services.rag_service import index_document
        count = await index_document("proj", "doc.md", "text", "text/plain")

    assert count == 1  # only the second chunk succeeded


# ── search ───────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_search_returns_ranked_results():
    """search vectorizes query and returns ranked results."""
    rows = [
        make_record(content="result1", filename="a.md", chunk_index=0, score=0.95),
        make_record(content="result2", filename="b.md", chunk_index=1, score=0.80),
    ]

    with (
        patch("services.rag_service.get_embedding", new_callable=AsyncMock, return_value=FAKE_VECTOR),
        patch("services.rag_service.fetch_all", new_callable=AsyncMock, return_value=rows),
    ):
        from services.rag_service import search
        results = await search("proj", "my query", top_k=5)

    assert len(results) == 2
    assert results[0].score == 0.95
    assert results[0].filename == "a.md"


@pytest.mark.asyncio
async def test_search_embedding_failure_returns_empty():
    """search returns empty list when query embedding fails."""
    with patch("services.rag_service.get_embedding", new_callable=AsyncMock, side_effect=RuntimeError("fail")):
        from services.rag_service import search
        results = await search("proj", "query")

    assert results == []


# ── delete_project_documents ─────────────────────────────────

@pytest.mark.asyncio
async def test_delete_project_documents():
    """delete_project_documents returns count from DELETE result."""
    with patch("services.rag_service.execute", new_callable=AsyncMock, return_value="DELETE 5"):
        from services.rag_service import delete_project_documents
        count = await delete_project_documents("proj")

    assert count == 5
