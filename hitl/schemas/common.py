"""Common Pydantic v2 schemas shared across routes."""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel


class ErrorResponse(BaseModel):
    """Structured error with a translation key."""

    key: str
    detail: Optional[str] = None


class SuccessResponse(BaseModel):
    """Generic success response."""

    ok: bool = True
    message: Optional[str] = None


class PaginationParams(BaseModel):
    """Pagination query parameters."""

    offset: int = 0
    limit: int = 50
