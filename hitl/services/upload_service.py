"""File upload service — save, extract text, list, delete."""

from __future__ import annotations

import mimetypes
import os
import re
from typing import Optional

import structlog

from core.config import settings
from core.database import execute, fetch_all

log = structlog.get_logger(__name__)


def _uploads_dir(slug: str) -> str:
    """Return the uploads directory for a project."""
    return os.path.join(settings.ag_flow_root, "projects", slug, "uploads")


def _sanitize_filename(name: str) -> str:
    """Remove unsafe characters from a filename."""
    # Keep only alphanumerics, dots, hyphens, underscores
    clean = re.sub(r"[^\w.\-]", "_", name)
    return clean[:200]


async def save_file(slug: str, filename: str, content: bytes) -> tuple[str, int]:
    """Save uploaded bytes to disk. Return (filepath, size)."""
    upload_dir = _uploads_dir(slug)
    os.makedirs(upload_dir, exist_ok=True)

    safe_name = _sanitize_filename(filename)
    filepath = os.path.join(upload_dir, safe_name)

    with open(filepath, "wb") as f:
        f.write(content)

    size = len(content)
    log.info("file_saved", slug=slug, filename=safe_name, size=size)
    return filepath, size


def extract_text(filepath: str) -> str:
    """Extract text content from a file. Returns empty string for unsupported types."""
    ext = os.path.splitext(filepath)[1].lower()

    if ext in (".md", ".txt", ".csv", ".json", ".yaml", ".yml", ".py", ".js", ".ts"):
        try:
            with open(filepath, "r", encoding="utf-8", errors="replace") as f:
                return f.read()
        except OSError:
            return ""

    if ext == ".pdf":
        return _extract_pdf(filepath)

    return ""


def _extract_pdf(filepath: str) -> str:
    """Extract text from a PDF file using pymupdf."""
    try:
        import fitz  # pymupdf
    except ImportError:
        log.warning("pymupdf_not_installed")
        return ""

    text_parts: list[str] = []
    try:
        doc = fitz.open(filepath)
        for page in doc:
            text_parts.append(page.get_text())
        doc.close()
    except Exception as exc:
        log.error("pdf_extraction_failed", filepath=filepath, error=str(exc))
        return ""

    return "\n".join(text_parts)


async def list_uploads(slug: str) -> list[dict]:
    """List uploaded files with metadata."""
    upload_dir = _uploads_dir(slug)
    if not os.path.isdir(upload_dir):
        return []

    result: list[dict] = []
    for name in sorted(os.listdir(upload_dir)):
        full = os.path.join(upload_dir, name)
        if not os.path.isfile(full):
            continue
        ct, _ = mimetypes.guess_type(name)
        result.append({
            "name": name,
            "size": os.path.getsize(full),
            "content_type": ct or "application/octet-stream",
        })
    return result


async def delete_upload(slug: str, filename: str) -> bool:
    """Delete a file from disk and remove its RAG documents."""
    safe_name = _sanitize_filename(filename)
    filepath = os.path.join(_uploads_dir(slug), safe_name)

    if os.path.isfile(filepath):
        os.remove(filepath)

    await execute(
        "DELETE FROM project.rag_documents WHERE project_slug = $1 AND filename = $2",
        slug, safe_name,
    )
    log.info("upload_deleted", slug=slug, filename=safe_name)
    return True
