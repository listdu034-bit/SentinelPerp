"""Route minute candles to raw storage and longer bars to retained views."""

from typing import Literal

from fastapi import APIRouter, Depends

from backend.api.dependencies import Symbol, TimeRange, filters, get_db
from backend.api.pagination import Page, Params, query_page
from backend.api.schemas import CandleResponse

router = APIRouter()


@router.get("/candles/{symbol}", response_model=Page[CandleResponse])
async def history(
    symbol: Symbol,
    interval: Literal["1m", "5m", "1h", "1d"] = "1m",
    bounds: TimeRange = Depends(),
    params: Params = Depends(),
    db=Depends(get_db),
):
    """Read retained OHLCV, newest first; aggregates follow DB refresh policy."""
    table = {
        "1m": "candles",
        "5m": "candles_5m",
        "1h": "candles_1h",
        "1d": "candles_1d",
    }[interval]
    where, args = filters(
        symbol, bounds, **({"interval": "1m"} if interval == "1m" else {})
    )
    projection = "*" if interval == "1m" else f"*, '{interval}' AS interval"
    return await query_page(
        db,
        f"SELECT {projection} FROM {table} WHERE {where} ORDER BY time DESC, exchange",
        args,
        params,
    )
