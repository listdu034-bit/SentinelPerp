"""Short-lived cached operational statistics."""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends

from backend.api.dependencies import get_db, get_redis
from backend.api.schemas import SystemStatusResponse

router = APIRouter()
TABLES = (
    "trades",
    "candles",
    "funding_rates",
    "open_interest",
    "liquidations",
    "orderbook_snapshots",
    "quality_logs",
)


async def system_status(db, redis):
    """Cache expensive exact retained-row counts for 30 seconds."""
    cached = await redis.get("api:status")
    if cached:
        return SystemStatusResponse.model_validate_json(cached)
    collection, sizes = {}, {}
    for table in TABLES:
        row = await db.fetchrow(
            f"SELECT count(*) AS count, max(time) AS latest_time FROM {table}"
        )
        collection[table] = dict(row)
        sizes[table] = await db.fetchval("SELECT hypertable_size($1::regclass)", table)
    memory = await redis.info("memory")
    connections = await db.fetchval(
        "SELECT count(*) FROM pg_stat_activity WHERE datname=current_database()"
    )
    incidents = await db.fetchval(
        "SELECT count(*) FROM quality_logs WHERE time >= now() - interval '24 hours'"
    )
    observations = await db.fetchval(
        "SELECT count(*) FROM trades WHERE time >= now() - interval '24 hours'"
    )
    result = SystemStatusResponse(
        time=datetime.now(timezone.utc),
        collection=collection,
        redis={"keys": await redis.dbsize(), "used_memory": memory["used_memory"]},
        database={"table_bytes": sizes, "connections": connections},
        quality_score=round(100 * max(0, 1 - incidents / max(1, observations)), 2),
    )
    await redis.set("api:status", result.model_dump_json(), ex=30)
    return result


@router.get("/status", response_model=SystemStatusResponse)
async def status(db=Depends(get_db), redis=Depends(get_redis)):
    """Retained counts, latest timestamps, storage sizes and 24h quality score.

    Score = max(0, 1 - incident count / max(1, trade count)) * 100.
    This is an operational indicator, not an exchange completeness guarantee.
    """
    return await system_status(db, redis)


async def market_snapshot(db, redis):
    """Rank observed 24h candle open-to-close changes; return both tails."""
    rows = await db.fetch(
        "WITH changes AS (SELECT symbol, "
        "100 * (last(close,time) / NULLIF(first(open,time),0) - 1) AS change_percent "
        "FROM candles WHERE interval='1m' AND time >= now() - interval '24 hours' "
        "GROUP BY symbol) "
        "(SELECT *, 'gainer' AS ranking FROM changes "
        "ORDER BY change_percent DESC, symbol LIMIT 10) "
        "UNION ALL "
        "(SELECT *, 'loser' AS ranking FROM changes "
        "ORDER BY change_percent, symbol LIMIT 10)"
    )
    return {
        "type": "market",
        "time": datetime.now(timezone.utc).isoformat(),
        "gainers": [dict(r) for r in rows if r["ranking"] == "gainer"],
        "losers": [dict(r) for r in rows if r["ranking"] == "loser"],
        "status": (await system_status(db, redis)).model_dump(mode="json"),
    }
