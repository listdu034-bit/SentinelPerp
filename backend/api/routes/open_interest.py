"""Paginated open-interest history."""

from fastapi import APIRouter, Depends

from backend.api.dependencies import Symbol, TimeRange, filters, get_db
from backend.api.pagination import Page, Params, query_page
from backend.api.schemas import OpenInterestResponse

router = APIRouter()


@router.get("/open-interest/{symbol}", response_model=Page[OpenInterestResponse])
async def history(
    symbol: Symbol,
    bounds: TimeRange = Depends(),
    params: Params = Depends(),
    db=Depends(get_db),
):
    """Return newest observations first; time bounds use [start, end)."""
    where, args = filters(symbol, bounds)
    return await query_page(
        db,
        f"SELECT * FROM open_interest WHERE {where} ORDER BY time DESC, exchange",
        args,
        params,
    )
