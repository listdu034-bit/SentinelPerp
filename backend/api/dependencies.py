"""Shared connection and validated query dependencies."""

from typing import Annotated

from fastapi import HTTPException, Path, Request
from pydantic import AwareDatetime

Symbol = Annotated[str, Path(pattern=r"^[A-Z0-9]+-USDT-SWAP$", max_length=80)]


async def get_db(request: Request):
    pool = request.app.state.database.pool
    if pool is None:
        raise HTTPException(503, "Database unavailable")
    async with pool.acquire() as connection:
        yield connection


def get_redis(request: Request):
    return request.app.state.redis.connection()


class TimeRange:
    """UTC-aware bounds, inclusive start and exclusive end."""

    def __init__(
        self,
        start_time: AwareDatetime | None = None,
        end_time: AwareDatetime | None = None,
    ):
        if start_time and end_time and start_time >= end_time:
            raise HTTPException(422, "start_time must precede end_time")
        self.start, self.end = start_time, end_time


def filters(symbol, bounds, **extra):
    clauses, args = [], []
    for column, value, operator in [
        ("symbol", symbol, "="),
        ("time", bounds.start, ">="),
        ("time", bounds.end, "<"),
        *((key, value, "=") for key, value in extra.items()),
    ]:
        if value is not None:
            args.append(value)
            clauses.append(f"{column} {operator} ${len(args)}")
    return " AND ".join(clauses) or "TRUE", args
