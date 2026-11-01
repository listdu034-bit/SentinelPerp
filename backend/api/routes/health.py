"""Liveness and dependency readiness probes."""

import asyncio

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

router = APIRouter()


@router.get("/health")
async def health():
    """Process liveness; use detailed health for readiness."""
    return {"status": "ok"}


@router.get("/health/detailed")
async def detailed(request: Request):
    """Check both dependencies without exposing credentials or server errors."""

    async def check_database():
        pool = request.app.state.database.pool
        if pool is None:
            return False
        return await pool.fetchval("SELECT 1") == 1

    async def probe(call):
        try:
            return bool(await asyncio.wait_for(call(), timeout=3))
        except Exception:
            return False

    database, redis = await asyncio.gather(
        probe(check_database), probe(request.app.state.redis.connection().ping)
    )
    healthy = database and redis
    return JSONResponse(
        {
            "status": "ok" if healthy else "degraded",
            "database": database,
            "redis": redis,
        },
        status_code=200 if healthy else 503,
    )
