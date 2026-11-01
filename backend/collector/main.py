"""Collector service lifecycle and signal handling."""

import asyncio
import signal
from contextlib import AsyncExitStack

import structlog

from backend.collector.cryptofeed_wrapper import CryptofeedWrapper
from backend.collector.deduplication import DeduplicationEngine
from backend.collector.instrument_discovery import InstrumentDiscovery
from backend.collector.quality_monitor import QualityMonitor
from backend.config.settings import get_settings
from backend.storage.redis_client import RedisClient
from backend.storage.timescale_client import TimescaleClient
from backend.utils.logger import configure_logging


async def run() -> None:
    """Start dependencies and fail loudly on unrecoverable storage failure."""
    settings = get_settings()
    configure_logging(settings.log_level)
    log = structlog.get_logger(__name__)
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stop.set)
    try:
        async with AsyncExitStack() as stack:
            redis = RedisClient(settings)
            database = TimescaleClient(settings)
            # Register cleanup before connect so partial startup is cleaned too.
            stack.push_async_callback(redis.close)
            stack.push_async_callback(database.close)
            async with asyncio.TaskGroup() as startup:
                startup.create_task(redis.connect())
                startup.create_task(database.connect())
            quality = QualityMonitor(settings, database, redis)
            dedup = DeduplicationEngine(settings, redis)
            wrapper = CryptofeedWrapper(settings, database, redis, dedup, quality)
            stack.push_async_callback(wrapper.close)
            discovery = InstrumentDiscovery(settings, wrapper.setup_feeds)
            stack.push_async_callback(discovery.close)
            await discovery.refresh_subscriptions()

            async def quality_loop() -> None:
                while True:
                    await quality.check_silence()
                    await asyncio.sleep(settings.quality_check_seconds)

            tasks = [
                asyncio.create_task(discovery.run(), name="discovery"),
                asyncio.create_task(wrapper.monitor(), name="feed-monitor"),
                asyncio.create_task(quality_loop(), name="quality"),
                asyncio.create_task(stop.wait(), name="shutdown-signal"),
            ]
            try:
                done, _ = await asyncio.wait(
                    [*tasks, database.worker],
                    return_when=asyncio.FIRST_COMPLETED,
                )
                for task in done:
                    await task
            finally:
                for task in tasks:
                    task.cancel()
                await asyncio.gather(*tasks, return_exceptions=True)
                log.info("collector_stopping")
    finally:
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.remove_signal_handler(sig)


def main() -> None:
    """Run the collector in an owned asyncio loop."""
    asyncio.run(run())


if __name__ == "__main__":
    main()
