"""Cached active OKX USDT perpetual catalog, using existing CCXT discovery."""

import asyncio
import json
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Request
from fastapi_pagination import paginate

from backend.api.dependencies import get_redis
from backend.api.pagination import Page, Params
from backend.api.schemas import InstrumentResponse

router = APIRouter()


@router.get("/instruments", response_model=Page[InstrumentResponse])
async def instruments(
    request: Request,
    symbol: str | None = None,
    params: Params = Depends(),
    redis=Depends(get_redis),
):
    """Search active symbols by case-insensitive substring; catalog TTL is 300s."""
    async with request.app.state.catalog_lock:
        cached = await redis.get("api:instruments")
        if cached:
            rows = json.loads(cached)
        else:
            symbols = await asyncio.wait_for(
                request.app.state.discovery.discover_instruments(), timeout=15
            )
            now = datetime.now(timezone.utc).isoformat()
            rows = [
                {"time": now, "symbol": s, "exchange": "OKX"} for s in sorted(symbols)
            ]
            await redis.set("api:instruments", json.dumps(rows), ex=300)
    if symbol:
        rows = [row for row in rows if symbol.upper() in row["symbol"]]
    return paginate(rows, params)
