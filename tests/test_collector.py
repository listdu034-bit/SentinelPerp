"""Offline behavioral tests using real Cryptofeed event types."""

import asyncio
import json
from datetime import datetime
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from cryptofeed.defines import CANDLES
from cryptofeed.symbols import Symbols
from cryptofeed.types import Candle as FeedCandle
from cryptofeed.types import OrderBook as FeedBook
from cryptofeed.types import Trade as FeedTrade
from pydantic import ValidationError

from backend.collector.cryptofeed_wrapper import CryptofeedWrapper, PublicOKX
from backend.collector.deduplication import DeduplicationEngine
from backend.collector.instrument_discovery import InstrumentDiscovery
from backend.collector.quality_monitor import QualityMonitor
from backend.config.settings import Settings
from backend.storage.models import Candle, Trade, utc_timestamp
from backend.storage.timescale_client import TimescaleClient


@pytest.fixture
def settings():
    return Settings(
        _env_file=None,
        dedup_mode="memory",
        batch_size=3,
        batch_flush_seconds=0.02,
        write_retry_attempts=2,
    )


def trade(ts=1700000000, trade_id="1"):
    return Trade(
        time=utc_timestamp(ts),
        receipt_timestamp=utc_timestamp(ts),
        symbol="BTC-USDT-SWAP",
        trade_id=trade_id,
        price="100.01",
        quantity="2",
        side="buy",
    )


async def test_dedup_concurrency_rollback_and_event_bucket(settings):
    engine = DeduplicationEngine(settings)
    tokens = await asyncio.gather(
        *[engine.reserve("trade", "BTC:1", 3601) for _ in range(20)]
    )
    assert sum(t is not None for t in tokens) == 1
    token = next(t for t in tokens if t)
    await engine.rollback(token)
    assert await engine.reserve("trade", "BTC:1", 3601) == token
    await engine.commit(token)
    assert await engine.reserve("trade", "BTC:1", 3601) is None
    assert engine.statistics()["duplicates"] == 20
    assert engine.cache_key("trade", "BTC:1", 3601).startswith("dedup:trade:1:")


async def test_dual_mode_survives_restart(settings):
    settings.dedup_mode = "dual"
    keys = set()
    redis = SimpleNamespace(
        seen=AsyncMock(side_effect=lambda key: key in keys),
        mark_seen=AsyncMock(side_effect=lambda key, ttl: keys.add(key)),
    )
    engine = DeduplicationEngine(settings, redis)
    token = await engine.reserve("trade", "BTC:2", 1)
    assert not keys  # uncommitted events are never cached as durable
    await engine.commit(token)
    restarted = DeduplicationEngine(settings, redis)
    assert await restarted.reserve("trade", "BTC:2", 1) is None
    assert restarted.statistics()["redis_hits"] == 1


async def test_memory_ttl(settings):
    settings.dedup_ttl_seconds = 1
    engine = DeduplicationEngine(settings)
    with patch("backend.collector.deduplication.time.monotonic", return_value=10):
        token = await engine.reserve("trade", "BTC:1", 1)
        await engine.commit(token)
    with patch("backend.collector.deduplication.time.monotonic", return_value=12):
        assert await engine.reserve("trade", "BTC:1", 1) is not None


async def start_writer(settings):
    db = TimescaleClient(settings)
    db.accepting = True
    db.worker = asyncio.create_task(db._writer())
    return db


async def test_batch_size_timer_and_shutdown(settings):
    db = await start_writer(settings)
    batches = []
    db.insert_batch = AsyncMock(side_effect=lambda rows: batches.append(rows))
    futures = [await db.submit(trade(trade_id=str(i))) for i in range(3)]
    await asyncio.gather(*futures)
    assert len(batches[0]) == 3
    await db.store(trade(trade_id="4"))  # timer flushes a partial batch
    last = await db.submit(trade(trade_id="5"))
    await db.close()  # shutdown flushes immediately
    assert last.done()
    assert [len(b) for b in batches] == [3, 1, 1]


async def test_writer_failure_reaches_pending_and_future_admission(settings):
    db = await start_writer(settings)
    gate = asyncio.Event()

    async def fail_batch(rows):
        await gate.wait()
        raise ValueError("schema failure")

    db.insert_batch = AsyncMock(side_effect=fail_batch)
    pending = [await db.submit(trade(trade_id=str(i))) for i in range(4)]
    gate.set()
    results = await asyncio.gather(*pending, return_exceptions=True)
    assert all(isinstance(r, ValueError) for r in results)
    with pytest.raises(RuntimeError):
        await db.submit(trade())
    with pytest.raises(ValueError):
        await db.close()


async def test_insert_retry_and_conflict_safety(settings):
    db = TimescaleClient(settings)
    conn = AsyncMock()
    conn.executemany.side_effect = [ConnectionResetError(), None]
    conn.transaction = MagicMock(return_value=AsyncMock())
    pool_context = AsyncMock()
    pool_context.__aenter__.return_value = conn
    db.pool = SimpleNamespace(acquire=lambda: pool_context)
    await db.insert_batch([trade()])
    assert conn.executemany.await_count == 2
    sql = conn.executemany.call_args.args[0]
    assert "ON CONFLICT DO NOTHING" in sql
    assert "INSERT INTO trades" in sql
    with pytest.raises(ValueError):
        await db.query(
            "trades; DROP TABLE trades", "BTC", utc_timestamp(1), utc_timestamp(2)
        )


async def test_quality_all_issues_and_nonregressing_watermarks(settings):
    db, redis = (
        SimpleNamespace(submit=AsyncMock()),
        SimpleNamespace(set_quality=AsyncMock()),
    )
    monitor = QualityMonitor(settings, db, redis)
    first = trade(trade_id="10")
    await monitor.check("trade", first)
    delayed = trade(ts=1700000001, trade_id="13").model_copy(
        update={
            "receipt_timestamp": utc_timestamp(1700000020),
        }
    )
    await monitor.check("trade", delayed)
    await monitor.check("trade", trade(ts=1699999990, trade_id="9"))
    assert monitor.trade_ids[first.symbol] == 13
    assert monitor.last_event[("trade", first.symbol)] == 1700000001
    issues = {call.args[0].issue_type for call in db.submit.call_args_list}
    assert {"gap", "latency", "staleness", "out_of_order"} <= issues
    count = db.submit.await_count
    await monitor.check_silence(1700000040)
    assert db.submit.await_count == count + 1
    await monitor.check_silence(1700000041)
    assert db.submit.await_count == count + 1  # one incident per silent period


async def make_wrapper(settings):
    db = await start_writer(settings)
    db.insert_batch = AsyncMock()
    redis = SimpleNamespace(set_latest=AsyncMock(), set_quality=AsyncMock())
    dedup = DeduplicationEngine(settings)
    quality = QualityMonitor(settings, db, redis)
    wrapper = CryptofeedWrapper(settings, db, redis, dedup, quality)
    return wrapper, db, redis


async def test_real_trade_duplicate_pipeline(settings):
    wrapper, db, redis = await make_wrapper(settings)
    obj = FeedTrade(
        "OKX",
        "BTC-USDT-PERP",
        "buy",
        Decimal("2"),
        Decimal("100.01"),
        1700000000.0,
        id="12",
    )
    await asyncio.gather(
        wrapper.on_trade(obj, 1700000000.1), wrapper.on_trade(obj, 1700000000.2)
    )
    await wrapper.close()
    await db.close()
    rows = [r for c in db.insert_batch.call_args_list for r in c.args[0]]
    trades = [r for r in rows if isinstance(r, Trade)]
    assert len(trades) == 1
    assert trades[0].symbol == "BTC-USDT-SWAP"
    assert trades[0].price == Decimal("100.01")
    assert redis.set_latest.await_count == 1
    assert wrapper.dedup.statistics()["duplicates"] == 1


async def test_failed_write_releases_dedup(settings):
    wrapper, db, _ = await make_wrapper(settings)
    db.insert_batch.side_effect = ConnectionError("offline")
    obj = FeedTrade(
        "OKX", "BTC-USDT-PERP", "buy", Decimal(2), Decimal(100), 1700000000.0, id="12"
    )
    await wrapper.on_trade(obj, 1700000000)
    with pytest.raises(ConnectionError):
        await wrapper.close()
    assert not wrapper.dedup.pending
    assert not wrapper.dedup.committed
    with pytest.raises(ConnectionError):
        await db.close()


async def test_real_book_and_closed_candles(settings):
    wrapper, db, _ = await make_wrapper(settings)
    book = FeedBook(
        "OKX",
        "BTC-USDT-PERP",
        bids={Decimal(99): Decimal(2)},
        asks={Decimal(101): Decimal(3)},
    )
    book.timestamp = 1700000000.0
    await wrapper.on_book(book, 1700000000.1)
    await wrapper.on_book(book, 1700000000.2)
    candle = FeedCandle(
        "OKX",
        "BTC-USDT-PERP",
        1699999980.0,
        1700000040.0,
        "1m",
        None,
        Decimal(100),
        Decimal(101),
        Decimal(102),
        Decimal(99),
        Decimal(5),
        True,
        1700000041.0,
        raw={
            "data": [["1699999980000", "100", "102", "99", "101", "5", "5", "500", "1"]]
        },
    )
    await wrapper.on_candle(candle, 1700000041.1)
    await wrapper.close()
    await db.close()
    rows = [r for c in db.insert_batch.call_args_list for r in c.args[0]]
    assert sum(type(r).__name__ == "OrderBookSnapshot" for r in rows) == 1
    assert sum(isinstance(r, Candle) for r in rows) == 1


async def test_discovery_filters_and_notifies(settings):
    callback = AsyncMock()
    discovery = InstrumentDiscovery(settings, callback)
    base = dict(swap=True, linear=True, quote="USDT", settle="USDT", active=True)
    discovery.exchange.load_markets = AsyncMock(
        return_value={
            "a": dict(base, id="BTC-USDT-SWAP"),
            "b": dict(base, id="ETH-USDT-SWAP", active=False),
            "c": dict(base, id="BTC-USD-SWAP", quote="USD"),
            "d": dict(base, id="BTC-USDT", swap=False),
        }
    )
    await discovery.refresh_subscriptions()
    await discovery.refresh_subscriptions()
    callback.assert_awaited_once_with({"BTC-USDT-SWAP"})
    await discovery.close()


async def test_business_subscription_uses_only_connection_channels(settings):
    Symbols.set("OKX", {"BTC-USDT-PERP": "BTC-USDT-SWAP"}, {})
    feed = PublicOKX(symbols=["BTC-USDT-PERP"], channels=[CANDLES])
    connection = SimpleNamespace(
        subscription={"candle": ["BTC-USDT-SWAP"]}, write=AsyncMock()
    )
    await feed.subscribe(connection)
    message = json.loads(connection.write.call_args.args[0])
    assert message["args"] == [{"channel": "candle1m", "instId": "BTC-USDT-SWAP"}]
    await feed.shutdown()


def test_validation_rejects_naive_time_bad_ohlc_and_infinite_price():
    with pytest.raises(ValidationError):
        Trade(**{**trade().model_dump(), "time": datetime(2025, 1, 1)})
    with pytest.raises(ValidationError):
        trade().model_validate({**trade().model_dump(), "price": "Infinity"})
    with pytest.raises(ValidationError):
        Candle(
            **trade().model_dump(
                exclude={"trade_id", "trade_count", "price", "quantity", "side"}
            ),
            open=10,
            high=5,
            low=1,
            close=4,
            volume=2,
        )


async def test_funding_interest_liquidation_real_types(settings):
    from cryptofeed.types import Funding as FeedFunding
    from cryptofeed.types import Liquidation as FeedLiquidation
    from cryptofeed.types import OpenInterest as FeedInterest

    from backend.storage.models import FundingRate, Liquidation, OpenInterest

    wrapper, db, _ = await make_wrapper(settings)
    now = 1700000000.0
    funding = FeedFunding(
        "OKX",
        "BTC-USDT-PERP",
        None,
        Decimal("0.0001"),
        None,
        now + 3600,
        raw={
            "ts": str(int(now * 1000)),
            "nextFundingTime": str(int((now + 3600) * 1000)),
        },
    )
    interest = FeedInterest("OKX", "BTC-USDT-PERP", Decimal(123), now)
    liquidation = FeedLiquidation(
        "OKX", "BTC-USDT-SWAP", "sell", Decimal(2), Decimal(100), None, "filled", now
    )
    await wrapper.on_funding(funding, now + 0.1)
    await wrapper.on_open_interest(interest, now + 0.1)
    await wrapper.on_liquidation(liquidation, now + 0.1)
    await wrapper.close()
    await db.close()
    rows = [r for c in db.insert_batch.call_args_list for r in c.args[0]]
    assert {type(r) for r in rows} == {FundingRate, OpenInterest, Liquidation}
    rate = next(r for r in rows if isinstance(r, FundingRate))
    assert rate.time.timestamp() == now
    assert rate.next_funding_time.timestamp() == now + 3600


async def test_feed_replacement_and_liquidation_shutdown(settings):
    wrapper, db, _ = await make_wrapper(settings)
    old = SimpleNamespace(stop=MagicMock(), shutdown=AsyncMock())
    new = SimpleNamespace(start=MagicMock(), stop=MagicMock(), shutdown=AsyncMock())
    wrapper.feed = old
    wrapper._build_feed = MagicMock(return_value=new)
    await wrapper.setup_feeds({"BTC-USDT-SWAP"})
    old.stop.assert_called_once()
    old.shutdown.assert_awaited_once()
    new.start.assert_called_once()
    await wrapper.close()
    new.shutdown.assert_awaited_once()
    await db.close()


async def test_invalid_trade_logs_validation_without_storage(settings):
    wrapper, db, _ = await make_wrapper(settings)
    bad = FeedTrade(
        "OKX", "BTC-USDT-PERP", "buy", Decimal(1), Decimal(-1), 1700000000.0, id="1"
    )
    await wrapper.on_trade(bad, 1700000000)
    await wrapper.close()
    await db.close()
    rows = [r for c in db.insert_batch.call_args_list for r in c.args[0]]
    assert len(rows) == 1
    assert rows[0].issue_type == "validation"


async def test_aggregated_trades_do_not_report_false_gaps(settings):
    database = SimpleNamespace(submit=AsyncMock())
    monitor = QualityMonitor(settings, database, SimpleNamespace())
    await monitor.check("trade", trade(trade_id="120"))
    aggregate = trade(ts=1700000001, trade_id="123").model_copy(
        update={"trade_count": 3}
    )
    await monitor.check("trade", aggregate)
    assert not database.submit.called
    await monitor.check("trade", trade(ts=1700000002, trade_id="126"))
    assert database.submit.call_args.args[0].details["missing"] == 2
