"""Paginated trades history."""

from fastapi import APIRouter, Depends, Query

from backend.api.dependencies import Symbol, TimeRange, filters, get_db
from backend.api.pagination import Page, Params, query_page
from backend.api.schemas import TradeResponse

router = APIRouter()


@router.get("/trades/{symbol}", response_model=Page[TradeResponse])
async def history(
    symbol: Symbol,
    bounds: TimeRange = Depends(),
    params: Params = Depends(),
    db=Depends(get_db),
    limit: int | None = Query(None, ge=1, le=1000),
):
    """Return newest observations first; time bounds use [start, end)."""
    if limit is not None:
        params = Params(page=params.page, size=limit)
    where, args = filters(symbol, bounds)
    return await query_page(
        db,
        f"SELECT * FROM trades WHERE {where} ORDER BY time DESC, trade_id DESC",
        args,
        params,
    )
