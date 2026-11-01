"""OKX feed adapter with normalization, quality, dedup and persistence."""

import asyncio
import hashlib
import json
from decimal import Decimal

import structlog
from cryptofeed.connection import WebsocketEndpoint
from cryptofeed.defines import (
    CANDLES,
    FUNDING,
    L2_BOOK,
    LIQUIDATIONS,
    OPEN_INTEREST,
    TRADES,
)
from cryptofeed.exchanges import OKX
from pydantic import ValidationError

from backend.collector.deduplication import DeduplicationEngine
from backend.collector.quality_monitor import QualityMonitor
from backend.config.settings import Settings
from backend.storage.models import (
    Candle,
    FundingRate,
    Liquidation,
    MarketEvent,
    OpenInterest,
    OrderBookSnapshot,
    Trade,
    utc_timestamp,
)
from backend.storage.redis_client import RedisClient
from backend.storage.timescale_client import TimescaleClient

log = structlog.get_logger(__name__)


class PublicOKX(OKX):
    """Route candles to OKX business WS; bound subscriptions per connection.

    Cryptofeed 2.5.0 still routes candles to public. Liquidations remain the
    upstream REST poller and are started by OKX.subscribe().
    """

    websocket_endpoints = [
        WebsocketEndpoint(
            "wss://ws.okx.com/ws/v5/public",
            channel_filter=tuple(
                OKX.websocket_channels[c]
                for c in (
                    TRADES,
                    L2_BOOK,
                    FUNDING,
                    OPEN_INTEREST,
                    LIQUIDATIONS,
                )
            ),
            limit=100,
            options={"compression": None},
        ),
        WebsocketEndpoint(
            "wss://ws.okx.com/ws/v5/business",
            channel_filter=(OKX.websocket_channels[CANDLES],),
            limit=100,
            options={"compression": None},
        ),
    ]

    async def subscribe(self, connection) -> None:
        """Send only this connection's channels to its assigned endpoint."""
        if LIQUIDATIONS in self.subscription:
            owner = getattr(self, "_liquidation_task", None)
            if owner is None or owner.done():
                self._liquidation_task = asyncio.create_task(
                    self._liquidations(self.subscription[LIQUIDATIONS])
                )
        channels = [
            self.build_subscription(channel, pair)
            for channel, pairs in connection.subscription.items()
            if channel != LIQUIDATIONS
            for pair in pairs
        ]
        if channels:
            await connection.write(json.dumps({"op": "subscribe", "args": channels}))

    async def _liquidations(self, pairs: list) -> None:
        # Upstream subscribe starts this coroutine on every reconnect. Keep one
        # owner per feed and retry the REST poller independently of WS traffic.
        existing = getattr(self, "_liquidation_owner", None)
        if existing is not None and not existing.done():
            return
        self._liquidation_owner = asyncio.current_task()
        try:
            while True:
                try:
                    await super()._liquidations(pairs)
                except Exception:
                    log.exception("liquidation_poll_failed")
                    await asyncio.sleep(5)
        finally:
            self._liquidation_owner = None

    async def shutdown(self) -> None:
        owner = getattr(self, "_liquidation_task", None)
        if owner is not None:
            owner.cancel()
            await asyncio.gather(owner, return_exceptions=True)
        await super().shutdown()


class CryptofeedWrapper:
    """Own feed lifecycle without taking over the application's event loop."""

    def __init__(
        self,
        settings: Settings,
        database: TimescaleClient,
        redis: RedisClient,
        dedup: DeduplicationEngine,
        quality: QualityMonitor,
    ):
        self.settings, self.database, self.redis = settings, database, redis
        self.dedup, self.quality = dedup, quality
        self.feed: PublicOKX | None = None
        self.symbols: set[str] = set()
        self.feed_tasks: set[asyncio.Task] = set()
        self.writes: set[asyncio.Task] = set()
        self.slots = asyncio.Semaphore(settings.buffer_max_size)
        self.lock = asyncio.Lock()
        self.failure = asyncio.get_running_loop().create_future()
        self.last_message: dict[str, float] = {}
        self.last_snapshot: dict[str, float] = {}
        self.closing = False

    def _build_feed(self, symbols: set[str]) -> PublicOKX:
        # Cryptofeed symbol lookup uses synchronous requests; call in a thread.
        mapping = PublicOKX.symbol_mapping(refresh=True)
        inverse = {native: normalized for normalized, native in mapping.items()}
        normalized = [inverse[s] for s in sorted(symbols)]
        return PublicOKX(
            symbols=normalized,
            channels=[TRADES, L2_BOOK, FUNDING, OPEN_INTEREST, LIQUIDATIONS, CANDLES],
            callbacks={
                TRADES: self.on_trade,
                L2_BOOK: self.on_book,
                FUNDING: self.on_funding,
                OPEN_INTEREST: self.on_open_interest,
                LIQUIDATIONS: self.on_liquidation,
                CANDLES: self.on_candle,
            },
            candle_interval="1m",
            candle_closed_only=True,
            max_depth=self.settings.orderbook_depth,
            timeout=self.settings.feed_timeout_seconds,
            retries=-1,
            config={"log": {"disabled": True}},
        )

    async def setup_feeds(self, symbols: set[str]) -> None:
        """Prepare a replacement before stopping the previous subscription."""
        async with self.lock:
            if self.closing:
                return
            feed = await asyncio.to_thread(self._build_feed, symbols)
            await self._stop_feed()
            self.feed = feed
            before = asyncio.all_tasks()
            feed.start(asyncio.get_running_loop())
            self.feed_tasks = asyncio.all_tasks() - before
            self.symbols = set(symbols)
            self.quality.retain_symbols(symbols)
            for symbol in symbols:
                self.quality.watch("trade", symbol)
                self.quality.watch("orderbook", symbol)
            log.info("subscriptions_started", instruments=len(symbols))

    async def _stop_feed(self) -> None:
        if self.feed is None:
            return
        self.feed.stop()
        for task in self.feed_tasks:
            task.cancel()
        await asyncio.gather(*self.feed_tasks, return_exceptions=True)
        await self.feed.shutdown()
        self.feed_tasks.clear()
        self.feed = None

    def connection_status(self) -> dict:
        """Report actual public connections and last callback times."""
        handlers = self.feed.connection_handlers if self.feed else []
        return {
            "instruments": len(self.symbols),
            "open_connections": sum(bool(c.conn.is_open) for c in handlers),
            "connections": len(handlers),
            "last_message": dict(self.last_message),
            "pending_writes": len(self.writes),
        }

    async def monitor(self) -> None:
        """Surface persistence failures and rebuild unexpectedly stopped feeds."""
        while True:
            if self.failure.done():
                raise self.failure.result()
            if self.feed_tasks and any(t.done() for t in self.feed_tasks):
                for task in self.feed_tasks:
                    if task.done() and not task.cancelled():
                        error = task.exception()
                        if error:
                            log.error("feed_task_failed", error=str(error))
                await self.setup_feeds(self.symbols)
            log.info(
                "collector_status",
                **self.connection_status(),
                dedup=self.dedup.statistics(),
            )
            await asyncio.sleep(self.settings.feed_reconnect_seconds)

    @staticmethod
    def native_symbol(symbol: str) -> str:
        """Map Cryptofeed perpetual notation to canonical OKX instrument ID."""
        if symbol.endswith("-PERP"):
            return symbol[:-5] + "-SWAP"
        return symbol

    def _common(self, obj, receipt: float, timestamp=None) -> dict:
        return {
            "time": utc_timestamp(obj.timestamp if timestamp is None else timestamp),
            "receipt_timestamp": utc_timestamp(receipt),
            "symbol": self.native_symbol(obj.symbol),
        }

    async def _persist(
        self,
        kind: str,
        event: MarketEvent,
        token: str,
        durability: asyncio.Future,
    ) -> None:
        try:
            await asyncio.shield(durability)
            await self.redis.set_latest(kind, event)
            await self.dedup.commit(token)
        except BaseException as error:
            await self.dedup.rollback(token)
            if not self.failure.done():
                self.failure.set_result(error)
            log.exception("event_persistence_failed", kind=kind, symbol=event.symbol)
        finally:
            self.slots.release()

    async def _handle(self, kind: str, obj, receipt: float, make_event) -> None:
        symbol = self.native_symbol(obj.symbol)
        self.last_message[kind] = receipt
        try:
            event = make_event()
        except (ValidationError, ValueError, TypeError, AttributeError) as error:
            await self.quality.issue(
                kind,
                symbol,
                "validation",
                {
                    "error": str(error),
                },
            )
            return
        # Candle event time is its start, not its transmission time.
        checked = event
        if isinstance(event, Candle):
            checked = event.model_copy(
                update={
                    "time": utc_timestamp(obj.timestamp or receipt),
                }
            )
        await self.quality.check(kind, checked)
        if isinstance(event, Trade):
            identity = f"{symbol}:{event.trade_id}"
        elif isinstance(event, Candle):
            identity = f"{symbol}:{event.interval}:{event.time.isoformat()}"
        elif isinstance(event, Liquidation):
            identity = f"{symbol}:{event.liquidation_id}"
        else:
            payload = event.model_dump(mode="json", exclude={"receipt_timestamp"})
            identity = json.dumps(payload, sort_keys=True)
        await self.slots.acquire()
        token = None
        try:
            token = await self.dedup.reserve(kind, identity, event.time.timestamp())
            if token is None:
                self.slots.release()
                return
            durability = await self.database.submit(event)
            task = asyncio.create_task(self._persist(kind, event, token, durability))
            self.writes.add(task)
            task.add_done_callback(self.writes.discard)
        except BaseException:
            if token is not None:
                await self.dedup.rollback(token)
            self.slots.release()
            raise

    async def on_trade(self, obj, receipt: float) -> None:
        """Normalize one executed trade."""
        await self._handle(
            "trade",
            obj,
            receipt,
            lambda: Trade(
                **self._common(obj, receipt),
                trade_id=str(obj.id) if obj.id is not None else "",
                trade_count=int((obj.raw or {}).get("count", 1)),
                price=obj.price,
                quantity=obj.amount,
                side=obj.side,
            ),
        )

    async def on_open_interest(self, obj, receipt: float) -> None:
        """Normalize outstanding contracts."""
        await self._handle(
            "open_interest",
            obj,
            receipt,
            lambda: OpenInterest(
                **self._common(obj, receipt),
                open_interest=obj.open_interest,
            ),
        )

    async def on_funding(self, obj, receipt: float) -> None:
        """Funding timestamp is settlement time, not observation time."""
        raw = obj.raw or {}
        observation = float(raw["ts"]) / 1000 if raw.get("ts") else receipt
        next_ts = raw.get("nextFundingTime") or raw.get("fundingTime")
        await self._handle(
            "funding",
            obj,
            receipt,
            lambda: FundingRate(
                **self._common(obj, receipt, observation),
                funding_rate=obj.rate,
                next_funding_time=(
                    utc_timestamp(float(next_ts) / 1000) if next_ts else None
                ),
            ),
        )

    async def on_liquidation(self, obj, receipt: float) -> None:
        """Use an exchange ID or a stable hash when OKX supplies none."""
        identity = (
            str(obj.id)
            if obj.id is not None
            else hashlib.sha256(
                f"{obj.symbol}:{obj.timestamp}:{obj.side}:{obj.quantity}:"
                f"{obj.price}:{obj.status}".encode()
            ).hexdigest()
        )
        await self._handle(
            "liquidation",
            obj,
            receipt,
            lambda: Liquidation(
                **self._common(obj, receipt),
                liquidation_id=identity,
                side=obj.side,
                quantity=obj.quantity,
                price=obj.price,
            ),
        )

    async def on_candle(self, obj, receipt: float) -> None:
        """Persist only confirmed closed 1m candles, not mutable updates."""
        raw = obj.raw or {}
        rows = raw.get("data", [])
        if rows and (len(rows[0]) < 9 or str(rows[0][8]) != "1"):
            return
        if not rows and not getattr(obj, "closed", False):
            return
        await self._handle(
            "candle",
            obj,
            receipt,
            lambda: Candle(
                **self._common(obj, receipt, obj.start),
                interval=obj.interval,
                open=obj.open,
                high=obj.high,
                low=obj.low,
                close=obj.close,
                volume=obj.volume,
            ),
        )

    async def on_book(self, obj, receipt: float) -> None:
        """Sample full reconstructed books once per minute; inspect all updates."""
        symbol = self.native_symbol(obj.symbol)
        self.last_message["orderbook"] = receipt
        try:
            depth = self.settings.orderbook_depth

            def levels(side, reverse):
                return sorted(
                    (
                        (Decimal(p), Decimal(q))
                        for p, q in side.to_dict().items()
                        if Decimal(q) > 0
                    ),
                    reverse=reverse,
                )[:depth]

            event = OrderBookSnapshot(
                **self._common(obj, receipt),
                bids=levels(obj.book.bids, True),
                asks=levels(obj.book.asks, False),
            )
        except (ValidationError, ValueError, TypeError, AttributeError) as error:
            await self.quality.issue(
                "orderbook",
                symbol,
                "validation",
                {
                    "error": str(error),
                },
            )
            return
        # Every update is monitored, even when not selected for history.
        if receipt - self.last_snapshot.get(symbol, 0) < (
            self.settings.orderbook_snapshot_seconds
        ):
            await self.quality.check("orderbook", event)
            await self.redis.set_latest("orderbook", event)
            return
        await self._handle("orderbook", obj, receipt, lambda: event)
        self.last_snapshot[symbol] = receipt

    async def close(self) -> None:
        """Stop sources, then await all admitted persistence operations."""
        async with self.lock:
            self.closing = True
            await self._stop_feed()
        await asyncio.gather(*self.writes)
        if self.failure.done():
            raise self.failure.result()
