"""File upload service — save, extract text, list, delete, archive extraction, git clone."""

from __future__ import annotations

import asyncio
import mimetypes
import os
import re
import shutil
import tarfile
import zipfile
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
    clean = re.sub(r"[^\w.\-]", "_", name)
    return clean[:200]


def _is_archive(filename: str) -> bool:
    """Check if a filename is a ZIP or TAR archive."""
    lower = filename.lower()
    return (
        lower.endswith(".zip")
        or lower.endswith(".tar")
        or lower.endswith(".tar.gz")
        or lower.endswith(".tgz")
        or lower.endswith(".tar.bz2")
        or lower.endswith(".tar.xz")
    )


def _archive_stem(filename: str) -> str:
    """Get the directory name for an extracted archive."""
    lower = filename.lower()
    name = filename
    for suffix in (".tar.gz", ".tar.bz2", ".tar.xz", ".tgz", ".tar", ".zip"):
        if lower.endswith(suffix):
            name = filename[: len(filename) - len(suffix)]
            break
    return _sanitize_filename(name)


def _extract_archive(filepath: str, dest_dir: str) -> list[str]:
    """Extract a ZIP or TAR archive into dest_dir. Return list of extracted file paths."""
    extracted: list[str] = []

    if zipfile.is_zipfile(filepath):
        with zipfile.ZipFile(filepath, "r") as zf:
            for member in zf.namelist():
                # Skip directories and hidden/system files
                if member.endswith("/") or "/.." in member or member.startswith("__MACOSX"):
                    continue
                zf.extract(member, dest_dir)
                extracted.append(os.path.join(dest_dir, member))
    elif tarfile.is_tarfile(filepath):
        with tarfile.open(filepath, "r:*") as tf:
            for member in tf.getmembers():
                if not member.isfile() or "/.." in member.name:
                    continue
                tf.extract(member, dest_dir, filter="data")
                extracted.append(os.path.join(dest_dir, member.name))

    return extracted


async def save_file(slug: str, filename: str, content: bytes) -> tuple[str, int, list[str]]:
    """Save uploaded bytes to disk.

    If the file is an archive (ZIP/TAR), it is extracted into a subdirectory
    and the archive file itself is removed.

    Returns (filepath_or_dir, size, extracted_files).
    extracted_files is empty for regular files.
    """
    upload_dir = _uploads_dir(slug)
    os.makedirs(upload_dir, exist_ok=True)

    safe_name = _sanitize_filename(filename)
    filepath = os.path.join(upload_dir, safe_name)

    with open(filepath, "wb") as f:
        f.write(content)

    size = len(content)

    # Auto-extract archives
    if _is_archive(filename):
        stem = _archive_stem(filename)
        dest_dir = os.path.join(upload_dir, stem)
        os.makedirs(dest_dir, exist_ok=True)
        extracted = _extract_archive(filepath, dest_dir)
        os.remove(filepath)  # Remove the archive after extraction
        log.info("archive_extracted", slug=slug, filename=safe_name, files=len(extracted))
        return dest_dir, size, extracted

    log.info("file_saved", slug=slug, filename=safe_name, size=size)
    return filepath, size, []


def extract_text(filepath: str) -> str:
    """Extract text content from a file. Returns empty string for unsupported types."""
    ext = os.path.splitext(filepath)[1].lower()

    if ext in (".md", ".txt", ".csv", ".json", ".yaml", ".yml", ".py", ".js", ".ts",
               ".jsx", ".tsx", ".html", ".css", ".xml", ".toml", ".ini", ".cfg",
               ".sh", ".bash", ".dart", ".kt", ".swift", ".java", ".go", ".rs",
               ".rb", ".php", ".sql", ".r", ".lua", ".env"):
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
    """List uploaded files and directories with metadata."""
    upload_dir = _uploads_dir(slug)
    if not os.path.isdir(upload_dir):
        return []

    result: list[dict] = []
    for name in sorted(os.listdir(upload_dir)):
        full = os.path.join(upload_dir, name)
        if os.path.isfile(full):
            ct, _ = mimetypes.guess_type(name)
            result.append({
                "name": name,
                "size": os.path.getsize(full),
                "content_type": ct or "application/octet-stream",
                "type": "file",
            })
        elif os.path.isdir(full):
            # Count files in directory
            file_count = sum(
                1 for _, _, files in os.walk(full) for _ in files
            )
            result.append({
                "name": name,
                "size": 0,
                "content_type": "directory",
                "type": "directory",
                "file_count": file_count,
            })
    return result


async def delete_upload(slug: str, filename: str) -> bool:
    """Delete a file or directory from disk and remove its RAG documents."""
    safe_name = _sanitize_filename(filename)
    path = os.path.join(_uploads_dir(slug), safe_name)

    if os.path.isfile(path):
        os.remove(path)
    elif os.path.isdir(path):
        shutil.rmtree(path, ignore_errors=True)

    # Remove RAG docs matching this name or prefixed by it (for directories)
    await execute(
        "DELETE FROM project.rag_documents WHERE project_slug = $1 AND (filename = $2 OR filename LIKE $3)",
        slug, safe_name, f"{safe_name}/%",
    )
    log.info("upload_deleted", slug=slug, filename=safe_name)
    return True


# ── Git clone into uploads ─────────────────────────────────────


async def clone_git_to_uploads(
    slug: str,
    repo_name: str,
    service: str = "other",
    url: str = "",
    login: str = "",
    token: str = "",
) -> tuple[str, list[str]]:
    """Clone a git repo into uploads/{repo_short_name}/.

    Returns (dest_dir, list_of_files).
    """
    from services.git_service import _build_clone_url
    from schemas.project import GitConfig

    # Build the short name for the directory
    short_name = repo_name.split("/")[-1] if "/" in repo_name else repo_name
    short_name = _sanitize_filename(short_name)

    upload_dir = _uploads_dir(slug)
    dest_dir = os.path.join(upload_dir, short_name)

    # Remove existing if present
    if os.path.isdir(dest_dir):
        shutil.rmtree(dest_dir)
    os.makedirs(upload_dir, exist_ok=True)

    config = GitConfig(service=service, url=url, login=login, token=token, repo_name=repo_name)
    clone_url = _build_clone_url(config)

    proc = await asyncio.create_subprocess_exec(
        "git", "clone", "--depth", "1", clone_url, dest_dir,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    _, stderr = await proc.communicate()
    if proc.returncode != 0:
        err_msg = stderr.decode("utf-8", errors="replace")[:300]
        log.error("git_clone_uploads_failed", slug=slug, repo=repo_name, error=err_msg)
        raise RuntimeError(f"git clone failed: {err_msg}")

    # Remove .git directory to save space
    git_dir = os.path.join(dest_dir, ".git")
    if os.path.isdir(git_dir):
        shutil.rmtree(git_dir)

    # Collect all files
    files: list[str] = []
    for root, _, filenames in os.walk(dest_dir):
        for fname in filenames:
            files.append(os.path.join(root, fname))

    log.info("git_cloned_to_uploads", slug=slug, repo=repo_name, files=len(files))
    return dest_dir, files
