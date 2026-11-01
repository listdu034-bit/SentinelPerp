"""Quality incidents and grouped counts."""

from typing import Literal

from fastapi import APIRouter, Depends

from backend.api.dependencies import TimeRange, filters, get_db
from backend.api.pagination import Page, Params, query_page
from backend.api.schemas import QualityLogResponse

router = APIRouter()


@router.get("/quality/logs", response_model=Page[QualityLogResponse])
async def logs(
    symbol: str | None = None,
    issue_type: str | None = None,
    severity: Literal["warning", "error"] | None = None,
    bounds: TimeRange = Depends(),
    params: Params = Depends(),
    db=Depends(get_db),
):
    """Combine optional filters; preserve structured incident details."""
    where, args = filters(symbol, bounds, issue_type=issue_type, severity=severity)
    return await query_page(
        db,
        f"SELECT * FROM quality_logs WHERE {where} ORDER BY time DESC, event_id DESC",
        args,
        params,
    )


@router.get("/quality/summary")
async def summary(bounds: TimeRange = Depends(), db=Depends(get_db)):
    """Count incidents by symbol and issue type over the selected time window."""
    where, args = filters(None, bounds)
    rows = await db.fetch(
        f"SELECT symbol, issue_type, count(*) AS count FROM quality_logs WHERE {where} "
        "GROUP BY symbol, issue_type ORDER BY symbol, issue_type",
        *args,
    )
    by_symbol, by_issue = {}, {}
    for row in rows:
        by_symbol[row["symbol"]] = by_symbol.get(row["symbol"], 0) + row["count"]
        by_issue[row["issue_type"]] = by_issue.get(row["issue_type"], 0) + row["count"]
    return {"by_symbol": by_symbol, "by_issue_type": by_issue}
