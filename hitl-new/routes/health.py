"""Health and version routes."""

from __future__ import annotations

import os

from fastapi import APIRouter

from core.database import get_pool

router = APIRouter(tags=["health"])

_VERSION: str = "dev"

# Try to read .version file at startup
for _vp in ["/project/.version", "/app/.version", os.path.join(os.path.dirname(__file__), "..", ".version")]:
    if os.path.isfile(_vp):
        try:
            with open(_vp, encoding="utf-8") as _f:
                _VERSION = _f.read().strip()
        except OSError:
            pass
        break


@router.get("/health")
async def health() -> dict:
    """Health check — reports DB connectivity."""
    db_ok = False
    try:
        pool = get_pool()
        async with pool.acquire() as conn:
            await conn.fetchval("SELECT 1")
        db_ok = True
    except Exception:
        pass
    return {"status": "ok" if db_ok else "degraded", "db": db_ok}


@router.get("/api/version")
async def version() -> dict:
    """Return service version."""
    return {"version": _VERSION, "service": "hitl-console"}
