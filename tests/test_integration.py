"""Opt-in integration checks against an initialized, dedicated test database.

Set TEST_DATABASE_URL and TEST_REDIS_URL after running init_db.sql. These tests
write uniquely named test symbols and remove their own data afterwards.
"""

import os
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import uuid4

import pytest

from backend.collector.deduplication import DeduplicationEngine
from backend.config.settings import Settings
from backend.storage.models import EVENT_TABLES, Trade
from backend.storage.redis_client import RedisClient
from backend.storage.timescale_client import TimescaleClient


@pytest.mark.skipif(
    not (os.getenv("TEST_DATABASE_URL") and os.getenv("TEST_REDIS_URL")),
    reason="Requires dedicated TimescaleDB and Redis test services",
)
async def test_database_retention_durable_dedup_and_latest():
    settings = Settings(
        _env_file=None,
        database_url=os.environ["TEST_DATABASE_URL"],
        redis_url=os.environ["TEST_REDIS_URL"],
        batch_flush_seconds=0.01,
    )
    database, redis = TimescaleClient(settings), RedisClient(settings)
    symbol = f"TEST{uuid4().hex}-USDT-SWAP"
    await database.connect()
    await redis.connect()
    token = None
    try:
        now = datetime.now(timezone.utc)
        event = Trade(
            time=now,
            receipt_timestamp=now,
            symbol=symbol,
            trade_id="1",
            price=Decimal("100.123456789"),
            quantity=Decimal("2"),
            side="buy",
        )
        await database.store(event)
        await database.store(event)  # database idempotency
        rows = await database.query(
            "trades",
            symbol,
            now - timedelta(days=365),
            now + timedelta(days=365),
        )
        assert len(rows) == 1
        assert rows[0]["price"] == event.price
        await redis.set_latest("trade", event)
        older = event.model_copy(update={"time": now - timedelta(days=365)})
        await redis.set_latest("trade", older)
        assert (await redis.get_latest("trade", symbol))["trade_id"] == "1"
        assert await redis.connection().ttl(f"latest:trade:{symbol}") > 0
        dedup = DeduplicationEngine(settings, redis)
        token = await dedup.reserve("trade", f"{symbol}:1", now.timestamp())
        await dedup.commit(token)
        restarted = DeduplicationEngine(settings, redis)
        assert await restarted.reserve("trade", f"{symbol}:1", now.timestamp()) is None
        async with database.transaction() as connection:
            hypertables = await connection.fetch(
                "SELECT hypertable_name FROM timescaledb_information.hypertables"
            )
            assert set(EVENT_TABLES.values()) <= {
                row["hypertable_name"] for row in hypertables
            }
            jobs = await connection.fetch(
                "SELECT config FROM timescaledb_information.jobs "
                "WHERE proc_name='policy_retention'"
            )
            assert len(jobs) >= 15  # seven raw tables plus eight CAGGs
            assert all("drop_after" in row["config"] for row in jobs)
    finally:
        async with database.transaction() as connection:
            await connection.execute("DELETE FROM trades WHERE symbol=$1", symbol)
        await redis.connection().delete(f"latest:trade:{symbol}")
        if token:
            await redis.connection().delete(token)
        await database.close()
        await redis.close()
