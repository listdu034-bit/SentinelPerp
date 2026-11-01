"""Paginated liquidations history."""

from typing import Literal

from fastapi import APIRouter, Depends

from backend.api.dependencies import Symbol, TimeRange, filters, get_db
from backend.api.pagination import Page, Params, query_page
from backend.api.schemas import LiquidationResponse

router = APIRouter()


@router.get("/liquidations/{symbol}", response_model=Page[LiquidationResponse])
async def history(
    symbol: Symbol,
    bounds: TimeRange = Depends(),
    params: Params = Depends(),
    db=Depends(get_db),
    side: Literal["buy", "sell"] | None = None,
):
    """Return newest observations first; time bounds use [start, end)."""
    where, args = filters(symbol, bounds, side=side)
    return await query_page(
        db,
        f"SELECT * FROM liquidations WHERE {where} "
        "ORDER BY time DESC, liquidation_id DESC",
        args,
        params,
    )
