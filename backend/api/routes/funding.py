"""Paginated funding history."""

from fastapi import APIRouter, Depends

from backend.api.dependencies import Symbol, TimeRange, filters, get_db
from backend.api.pagination import Page, Params, query_page
from backend.api.schemas import FundingRateResponse

router = APIRouter()


@router.get("/funding/{symbol}", response_model=Page[FundingRateResponse])
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
        f"SELECT * FROM funding_rates WHERE {where} ORDER BY time DESC, exchange",
        args,
        params,
    )
