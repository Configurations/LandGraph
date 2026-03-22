"""Health check endpoint."""

from fastapi import APIRouter

from core.database import get_pool

router = APIRouter()


@router.get("/health")
async def health() -> dict:
    """Return service health with DB connectivity check."""
    db_ok = False
    try:
        pool = get_pool()
        async with pool.acquire() as conn:
            await conn.fetchval("SELECT 1")
        db_ok = True
    except Exception:
        pass
    status = "ok" if db_ok else "degraded"
    return {"status": status, "db": db_ok}
