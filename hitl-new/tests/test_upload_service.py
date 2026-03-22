"""Tests for services/upload_service.py."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, mock_open, patch

import pytest


# ── save_file ────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_save_file_writes_to_disk():
    """save_file creates dir, writes bytes, returns path and size."""
    content = b"hello world"

    m = mock_open()
    with (
        patch("services.upload_service.os.makedirs") as mk,
        patch("builtins.open", m),
    ):
        from services.upload_service import save_file
        filepath, size = await save_file("proj", "readme.md", content)

    mk.assert_called_once()
    m().write.assert_called_once_with(content)
    assert size == 11
    assert "readme.md" in filepath


# ── extract_text ─────────────────────────────────────────────

def test_extract_text_md_file():
    """extract_text reads .md files as UTF-8."""
    m = mock_open(read_data="# Hello")
    with patch("builtins.open", m):
        from services.upload_service import extract_text
        result = extract_text("/tmp/doc.md")
    assert result == "# Hello"


def test_extract_text_txt_file():
    """extract_text reads .txt files."""
    m = mock_open(read_data="plain text")
    with patch("builtins.open", m):
        from services.upload_service import extract_text
        result = extract_text("/tmp/file.txt")
    assert result == "plain text"


def test_extract_text_pdf():
    """extract_text extracts text from PDF via fitz."""
    mock_page = MagicMock()
    mock_page.get_text.return_value = "PDF content"

    mock_doc = MagicMock()
    mock_doc.__iter__ = lambda self: iter([mock_page])
    mock_doc.close = MagicMock()

    mock_fitz = MagicMock()
    mock_fitz.open.return_value = mock_doc

    with patch.dict("sys.modules", {"fitz": mock_fitz}):
        from services.upload_service import _extract_pdf
        result = _extract_pdf("/tmp/file.pdf")

    assert "PDF content" in result


def test_extract_text_unknown_type():
    """extract_text returns empty for unsupported extensions."""
    from services.upload_service import extract_text
    result = extract_text("/tmp/file.xyz")
    assert result == ""


# ── list_uploads ─────────────────────────────────────────────

@pytest.mark.asyncio
async def test_list_uploads_returns_metadata():
    """list_uploads returns file names, sizes, content types."""
    # Ensure mimetypes is initialised before we patch os.path.isfile,
    # otherwise mimetypes.init() sees fake isfile results and tries to
    # open /etc/mime.types (which doesn't exist on all platforms).
    import mimetypes as _mt
    _mt.init()

    with (
        patch("services.upload_service.os.path.isdir", return_value=True),
        patch("services.upload_service.os.listdir", return_value=["a.md", "b.pdf"]),
        patch("services.upload_service.os.path.isfile", return_value=True),
        patch("services.upload_service.os.path.getsize", return_value=1234),
    ):
        from services.upload_service import list_uploads
        result = await list_uploads("proj")

    assert len(result) == 2
    assert result[0]["name"] == "a.md"
    assert result[0]["size"] == 1234


@pytest.mark.asyncio
async def test_list_uploads_empty_dir():
    """list_uploads returns empty list when dir doesn't exist."""
    with patch("services.upload_service.os.path.isdir", return_value=False):
        from services.upload_service import list_uploads
        result = await list_uploads("proj")
    assert result == []


# ── delete_upload ────────────────────────────────────────────

@pytest.mark.asyncio
async def test_delete_upload_removes_file_and_db():
    """delete_upload removes file from disk and RAG documents."""
    with (
        patch("services.upload_service.os.path.isfile", return_value=True),
        patch("services.upload_service.os.remove") as rm,
        patch("services.upload_service.execute", new_callable=AsyncMock),
    ):
        from services.upload_service import delete_upload
        result = await delete_upload("proj", "readme.md")

    assert result is True
    rm.assert_called_once()
