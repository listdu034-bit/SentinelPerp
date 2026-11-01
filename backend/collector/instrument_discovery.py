"""Discover active linear USDT perpetual instruments using async CCXT."""

import asyncio
from fnmatch import fnmatchcase
from typing import Awaitable, Callable

import ccxt.async_support as ccxt
import structlog
from tenacity import (
    AsyncRetrying,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from backend.config.settings import Settings

log = structlog.get_logger(__name__)


class InstrumentDiscovery:
    """Refresh markets every 300s and notify the subscription owner."""

    def __init__(
        self,
        settings: Settings,
        on_change: Callable[[set[str]], Awaitable[None]],
    ):
        self.settings, self.on_change = settings, on_change
        self.exchange = ccxt.okx({"enableRateLimit": True})
        self.exchange.urls["api"]["rest"] = settings.okx_rest_url
        self.symbols: set[str] = set()
        self.initialized = False

    async def discover_instruments(self) -> set[str]:
        """Fetch markets; filter on OKX native IDs, not CCXT symbols."""
        markets = await self.exchange.load_markets(reload=True)
        return {
            market["id"]
            for market in markets.values()
            if market.get("swap")
            and market.get("linear")
            and market.get("quote") == "USDT"
            and market.get("settle") == "USDT"
            and market.get("active") is not False
            and fnmatchcase(market["id"], self.settings.okx_market_filter)
            and market["id"].endswith("-USDT-SWAP")
        }

    async def refresh_subscriptions(self) -> None:
        """Apply additions/removals only after the owner accepts the update."""
        async for attempt in AsyncRetrying(
            retry=retry_if_exception_type(ccxt.NetworkError),
            stop=stop_after_attempt(self.settings.write_retry_attempts),
            wait=wait_exponential(max=self.settings.retry_max_seconds),
            reraise=True,
        ):
            with attempt:
                symbols = await self.discover_instruments()
        if not symbols:
            raise RuntimeError("OKX returned no eligible active instruments")
        if not self.initialized or symbols != self.symbols:
            await self.on_change(symbols)
            log.info(
                "instruments_changed",
                added=sorted(symbols - self.symbols),
                removed=sorted(self.symbols - symbols),
            )
            self.symbols, self.initialized = symbols, True

    async def run(self) -> None:
        """Retry failed refreshes without discarding working subscriptions."""
        while True:
            try:
                await self.refresh_subscriptions()
            except Exception:
                log.exception("instrument_refresh_failed")
            await asyncio.sleep(self.settings.instrument_refresh_seconds)

    async def close(self) -> None:
        """Close CCXT's HTTP session."""
        await self.exchange.close()
