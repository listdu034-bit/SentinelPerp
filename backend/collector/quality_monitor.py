"""Per-stream event quality and independent silence monitoring."""

import time
from collections import defaultdict
from datetime import datetime, timezone

import structlog

from backend.config.settings import Settings
from backend.storage.models import MarketEvent, QualityLog, Trade
from backend.storage.redis_client import RedisClient
from backend.storage.timescale_client import TimescaleClient

log = structlog.get_logger(__name__)


class QualityMonitor:
    """Record all problems; high watermarks never move backwards."""

    def __init__(
        self,
        settings: Settings,
        database: TimescaleClient,
        redis: RedisClient,
    ):
        self.settings, self.database, self.redis = settings, database, redis
        self.last_event: dict[tuple[str, str], float] = {}
        self.last_received: dict[tuple[str, str], float] = {}
        self.trade_ids: dict[str, int] = {}
        self.stale_reported: set[tuple[str, str]] = set()
        self.metrics: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))

    def watch(self, kind: str, symbol: str) -> None:
        """Monitor a high-frequency stream even before its first event."""
        self.last_received.setdefault((kind, symbol), time.time())

    def retain_symbols(self, symbols: set[str]) -> None:
        """Remove delisted symbols from the silence monitor."""
        self.last_received = {
            key: value for key, value in self.last_received.items() if key[1] in symbols
        }
        self.last_event = {
            key: value for key, value in self.last_event.items() if key[1] in symbols
        }
        self.trade_ids = {
            key: value for key, value in self.trade_ids.items() if key in symbols
        }
        self.stale_reported.intersection_update(self.last_received)

    async def issue(
        self,
        kind: str,
        symbol: str,
        issue: str,
        details: dict,
    ) -> None:
        """Queue a durable incident; writer failures terminate the service."""
        self.metrics[symbol][issue] += 1
        log.warning(
            "data_quality",
            data_type=kind,
            symbol=symbol,
            issue_type=issue,
            details=details,
        )
        await self.database.submit(
            QualityLog(
                time=datetime.now(timezone.utc),
                data_type=kind,
                symbol=symbol,
                issue_type=issue,
                details=details,
            )
        )

    async def check(self, kind: str, event: MarketEvent) -> None:
        """Check latency, ordering, staleness and numeric trade-ID gaps."""
        symbol = event.symbol
        key = kind, symbol
        ts = event.time.timestamp()
        receipt = event.receipt_timestamp.timestamp()
        self.metrics[symbol]["received"] += 1
        latency = (receipt - ts) * 1000
        if latency > self.settings.trade_max_latency_ms or latency < -2000:
            await self.issue(kind, symbol, "latency", {"latency_ms": latency})
        previous = self.last_event.get(key)
        if (
            previous is not None
            and (previous - ts) * 1000 > self.settings.out_of_order_tolerance_ms
        ):
            await self.issue(
                kind,
                symbol,
                "out_of_order",
                {
                    "previous": previous,
                    "current": ts,
                },
            )
        if receipt - ts > self.settings.trade_stale_seconds:
            await self.issue(
                kind,
                symbol,
                "staleness",
                {
                    "age_seconds": receipt - ts,
                },
            )
        self.last_event[key] = max(ts, previous or ts)
        self.last_received[key] = max(receipt, self.last_received.get(key, 0))
        self.stale_reported.discard(key)
        if isinstance(event, Trade) and self.settings.trade_id_gap_detection:
            if event.trade_id.isdecimal():
                current = int(event.trade_id)
                last = self.trade_ids.get(symbol)
                first = current - event.trade_count + 1
                if last is not None and first > last + 1:
                    await self.issue(
                        kind,
                        symbol,
                        "gap",
                        {
                            "last_trade_id": last,
                            "current_trade_id": current,
                            "missing": first - last - 1,
                            "aggregate_count": event.trade_count,
                            "note": "ID discontinuity; not proof of lost trades",
                        },
                    )
                self.trade_ids[symbol] = max(current, last or current)

    async def check_silence(self, now: float | None = None) -> None:
        """Detect silent trade/book streams independently of callbacks.

        Funding/OI/liquidations are sparse by nature and are excluded from
        the 15-second no-message rule; their event latency is still checked.
        """
        now = time.time() if now is None else now
        for (kind, symbol), last in list(self.last_received.items()):
            key = kind, symbol
            if kind not in ("trade", "orderbook"):
                continue
            if (
                now - last > self.settings.trade_stale_seconds
                and key not in self.stale_reported
            ):
                await self.issue(
                    kind,
                    symbol,
                    "staleness",
                    {
                        "silence_seconds": now - last,
                    },
                )
                self.stale_reported.add(key)
        for symbol, metrics in list(self.metrics.items()):
            await self.redis.set_quality(symbol, dict(metrics))
