"""RAG service — embedding, chunking, indexing, similarity search."""

from __future__ import annotations

import json
import os
from typing import Any, Optional

import httpx
import structlog

from core.config import load_json_config, settings
from core.database import execute, fetch_all, get_pool
from schemas.rag import RagSearchResult

log = structlog.get_logger(__name__)

# ── Embedding provider resolution ─────────────────


def _find_embedding_provider(provider_id: str = "") -> Optional[dict[str, Any]]:
    """Find an embedding-capable provider in llm_providers.json.

    If provider_id is given, return that specific provider.
    Otherwise, return the first provider with embedding: true.
    """
    data = load_json_config("llm_providers.json")
    providers_dict = data.get("providers", {})

    # If a specific provider is requested, return it directly
    if provider_id and isinstance(providers_dict, dict) and provider_id in providers_dict:
        return providers_dict[provider_id]

    providers = list(providers_dict.values()) if isinstance(providers_dict, dict) else providers_dict
    for p in providers:
        if not isinstance(p, dict):
            continue
        if p.get("embedding") is True:
            return p
        ptype = str(p.get("type", ""))
        if "embedding" in ptype.lower():
            return p
    return None


async def get_embedding(text: str, provider_id: str = "") -> list[float]:
    """Get an embedding vector for the given text (single attempt, no retry)."""
    provider = _find_embedding_provider(provider_id)
    if not provider:
        raise RuntimeError("rag.no_embedding_provider")

    ptype = provider.get("type", "openai")
    model = provider.get("model", "text-embedding-3-small")
    env_key = provider.get("env_key", "")
    api_key = provider.get("api_key", "") or (os.getenv(env_key, "") if env_key else "")

    if ptype in ("openai", "azure_openai"):
        return await _embed_openai(provider, model, api_key, text)
    if ptype == "ollama":
        return await _embed_ollama(provider, model, text)
    raise RuntimeError(f"rag.unsupported_embedding_type:{ptype}")


async def _embed_openai(
    provider: dict[str, Any], model: str, api_key: str, text: str,
) -> list[float]:
    """Call OpenAI-compatible embeddings endpoint."""
    base_url = provider.get("base_url", "https://api.openai.com/v1")
    url = f"{base_url}/embeddings"
    headers = {"Authorization": f"Bearer {api_key}"}
    body = {"model": model, "input": text}

    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(url, headers=headers, json=body)
        resp.raise_for_status()
    data = resp.json()
    return data["data"][0]["embedding"]


async def _embed_ollama(
    provider: dict[str, Any], model: str, text: str,
) -> list[float]:
    """Call Ollama embeddings endpoint."""
    base_url = provider.get("base_url", "http://localhost:11434")
    url = f"{base_url}/api/embeddings"
    body = {"model": model, "prompt": text}

    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.post(url, json=body)
        resp.raise_for_status()
    data = resp.json()
    return data["embedding"]


# ── Text chunking ──────────────────────────────────


def chunk_text(
    text: str,
    max_tokens: int = 128,
    overlap: int = 20,
) -> list[str]:
    """Split text into overlapping chunks for embedding."""
    if not text.strip():
        return []

    paragraphs = text.split("\n\n")
    chunks: list[str] = []
    current: list[str] = []
    current_len = 0

    for para in paragraphs:
        para_len = _approx_tokens(para)
        if para_len > max_tokens:
            # Flush current
            if current:
                chunks.append("\n\n".join(current))
                current, current_len = [], 0
            # Split large paragraph by lines then sentences
            sub_chunks = _split_large_block(para, max_tokens, overlap)
            chunks.extend(sub_chunks)
            continue

        if current_len + para_len > max_tokens and current:
            chunks.append("\n\n".join(current))
            # Keep overlap from the end
            overlap_text = _take_tail_tokens(current, overlap)
            current = [overlap_text] if overlap_text else []
            current_len = _approx_tokens(overlap_text) if overlap_text else 0

        current.append(para)
        current_len += para_len

    if current:
        chunks.append("\n\n".join(current))

    # Merge tiny chunks with previous (only if combined stays under max)
    merge_threshold = max_tokens // 4
    merged: list[str] = []
    for chunk in chunks:
        if merged and _approx_tokens(chunk) < merge_threshold and _approx_tokens(merged[-1] + "\n\n" + chunk) <= max_tokens:
            merged[-1] = merged[-1] + "\n\n" + chunk
        else:
            merged.append(chunk)

    return merged


def _approx_tokens(text: str) -> int:
    """Rough token count (~4 chars per token)."""
    return len(text) // 4 + 1


def _take_tail_tokens(parts: list[str], token_limit: int) -> str:
    """Take text from the tail of parts up to token_limit."""
    result: list[str] = []
    total = 0
    for part in reversed(parts):
        t = _approx_tokens(part)
        if total + t > token_limit:
            break
        result.insert(0, part)
        total += t
    return "\n\n".join(result)


def _split_large_block(
    text: str, max_tokens: int, overlap: int,
) -> list[str]:
    """Split a large block by lines, then by sentences if needed."""
    lines = text.split("\n")
    chunks: list[str] = []
    current: list[str] = []
    current_len = 0

    for line in lines:
        line_len = _approx_tokens(line)
        if current_len + line_len > max_tokens and current:
            chunks.append("\n".join(current))
            current, current_len = [], 0
        current.append(line)
        current_len += line_len

    if current:
        chunks.append("\n".join(current))
    return chunks


# ── Indexing & search ──────────────────────────────


async def index_document(
    project_slug: str,
    filename: str,
    content: str,
    content_type: str,
    embedding_provider: str = "",
) -> int:
    """Chunk text, compute embeddings, store in rag_documents."""
    # Remove old entries for this file
    await execute(
        "DELETE FROM project.rag_documents WHERE project_slug = $1 AND filename = $2",
        project_slug, filename,
    )

    chunks = chunk_text(content)
    if not chunks:
        return 0

    pool = get_pool()
    count = 0
    for idx, chunk in enumerate(chunks):
        try:
            vec = await get_embedding(chunk, provider_id=embedding_provider)
        except Exception as exc:
            log.error("embedding_failed", chunk_index=idx, error=str(exc))
            continue

        vec_str = "[" + ",".join(str(v) for v in vec) + "]"
        await pool.execute(
            """INSERT INTO project.rag_documents
               (project_slug, filename, content_type, chunk_index, content, embedding)
               VALUES ($1, $2, $3, $4, $5, $6::vector)""",
            project_slug, filename, content_type, idx, chunk, vec_str,
        )
        count += 1

    log.info("rag_indexed", slug=project_slug, filename=filename, chunks=count)
    return count


async def search(
    project_slug: str,
    query: str,
    top_k: int = 5,
    embedding_provider: str = "",
) -> list[RagSearchResult]:
    """Semantic similarity search over project documents."""
    try:
        query_vec = await get_embedding(query, provider_id=embedding_provider)
    except Exception as exc:
        log.error("rag_search_embedding_failed", error=str(exc))
        return []

    vec_str = "[" + ",".join(str(v) for v in query_vec) + "]"
    rows = await fetch_all(
        """SELECT content, filename, chunk_index,
                  1 - (embedding <=> $1::vector) AS score
           FROM project.rag_documents
           WHERE project_slug = $2
           ORDER BY embedding <=> $1::vector
           LIMIT $3""",
        vec_str, project_slug, top_k,
    )

    return [
        RagSearchResult(
            content=r["content"],
            filename=r["filename"],
            chunk_index=r["chunk_index"],
            score=float(r["score"]),
            metadata={},
        )
        for r in rows
    ]


async def delete_project_documents(project_slug: str) -> int:
    """Delete all RAG documents for a project."""
    result = await execute(
        "DELETE FROM project.rag_documents WHERE project_slug = $1",
        project_slug,
    )
    # asyncpg returns "DELETE N"
    parts = result.split()
    count = int(parts[-1]) if len(parts) >= 2 else 0
    log.info("rag_documents_deleted", slug=project_slug, count=count)
    return count
