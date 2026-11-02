"""Opt-in API checks against a dedicated initialized TimescaleDB and Redis."""

import asyncio
import json
import os
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from backend.api.limiter import limiter
from backend.api.main import create_app
from backend.config.settings import Settings
from backend.storage.models import (
    Candle,
    FundingRate,
    Liquidation,
    OpenInterest,
    QualityLog,
    Trade,
)
from backend.storage.redis_client import RedisClient
from backend.storage.timescale_client import TimescaleClient

pytestmark = pytest.mark.skipif(
    not (os.getenv("TEST_DATABASE_URL") and os.getenv("TEST_REDIS_URL")),
    reason="Requires dedicated TimescaleDB and Redis test services",
)


def test_api_real_database_and_redis_broadcast():
    settings = Settings(
        _env_file=None,
        database_url=os.environ["TEST_DATABASE_URL"],
        redis_url=os.environ["TEST_REDIS_URL"],
        write_retry_attempts=1,
        m2_scheduler_enabled=False,  # Keep API regression independent of OKX jobs.
    )
    symbol = f"TEST{uuid4().hex.upper()}-USDT-SWAP"
    now = datetime.now(timezone.utc).replace(second=0, microsecond=0) - timedelta(
        minutes=10
    )
    common = dict(time=now, receipt_timestamp=now, symbol=symbol)
    trade = Trade(**common, trade_id="1", price="123.125", quantity=2, side="buy")

    async def seed():
        database, redis = TimescaleClient(settings), RedisClient(settings)
        await database.connect()
        await redis.connect()
        try:
            await database.insert_batch(
                [
                    trade,
                    trade.model_copy(
                        update={"trade_id": "2", "time": now + timedelta(seconds=1)}
                    ),
                    Candle(**common, open=100, high=130, low=99, close=125, volume=2),
                    FundingRate(**common, funding_rate="0.0001"),
                    OpenInterest(**common, open_interest=100),
                    Liquidation(
                        **common, liquidation_id="1", side="sell", quantity=1, price=120
                    ),
                    QualityLog(
                        time=now, symbol=symbol, data_type="trade", issue_type="gap"
                    ),
                ]
            )
            async with database.pool.acquire() as db:
                for view in ("candles_5m", "candles_1h", "candles_1d"):
                    await db.execute(
                        f"CALL refresh_continuous_aggregate('{view}', "
                        "$1::timestamptz, $2::timestamptz)",
                        now - timedelta(days=3),
                        now + timedelta(days=2),
                    )
            await redis.connection().delete("api:status")
            await redis.connection().set(
                "api:instruments",
                json.dumps(
                    [{"symbol": symbol, "time": now.isoformat(), "exchange": "OKX"}]
                ),
                ex=60,
            )
        finally:
            await redis.close()
            await database.close()

    async def cleanup():
        database, redis = TimescaleClient(settings), RedisClient(settings)
        await database.connect()
        await redis.connect()
        try:
            async with database.pool.acquire() as db:
                for table in (
                    "trades",
                    "candles",
                    "funding_rates",
                    "open_interest",
                    "liquidations",
                    "quality_logs",
                ):
                    await db.execute(f"DELETE FROM {table} WHERE symbol=$1", symbol)
            await redis.connection().delete(
                "api:status", "api:instruments", f"latest:trade:{symbol}"
            )
        finally:
            await redis.close()
            await database.close()

    asyncio.run(seed())
    limiter.reset()
    app = create_app(settings)
    try:
        with TestClient(app) as client:
            assert client.get("/health/detailed").status_code == 200
            for resource in ("trades", "funding", "open-interest", "liquidations"):
                response = client.get(f"/api/v1/{resource}/{symbol}")
                assert response.status_code == 200, response.text
                assert response.json()["total"] >= 1
            result = client.get(f"/api/v1/trades/{symbol}?size=1&page=2").json()
            assert result["total"] == 2 and result["items"][0]["trade_id"] == "1"
            assert result["items"][0]["price"] == 123.125
            for interval in ("1m", "5m", "1h", "1d"):
                response = client.get(f"/api/v1/candles/{symbol}?interval={interval}")
                assert response.status_code == 200, response.text
                assert response.json()["items"][0]["close"] == 125
            assert (
                client.get(f"/api/v1/instruments?symbol={symbol}").json()["total"] == 1
            )
            assert (
                client.get(f"/api/v1/quality/logs?symbol={symbol}").json()["total"] == 1
            )
            assert symbol in client.get("/api/v1/quality/summary").json()["by_symbol"]
            response = client.get("/api/v1/status")
            assert response.status_code == 200, response.text
            assert response.json()["database"]["table_bytes"]["trades"] > 0
            with client.websocket_connect(f"/ws/trades/{symbol}") as ws:
                assert ws.receive_json()["type"] == "subscribed"
                client.portal.call(app.state.redis.set_latest, "trade", trade)
                event = ws.receive_json()
                assert event["type"] == "trade" and event["data"]["price"] == 123.125
            with client.websocket_connect("/ws/market") as ws:
                snapshot = ws.receive_json()
                assert snapshot["type"] == "market"
                assert "status" in snapshot and len(snapshot["gainers"]) <= 10
            metrics = client.get("/metrics").text
            assert (
                "http_requests_total" in metrics
                and "http_requests_inprogress" in metrics
            )
    finally:
        asyncio.run(cleanup())
