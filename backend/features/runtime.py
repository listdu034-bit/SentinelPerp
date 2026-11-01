"""APScheduler jobs owned and drained by the API lifespan."""

import asyncio
import logging
from datetime import datetime, timedelta, timezone

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from backend.analysis.service import FeatureExtractionService
from backend.cases.service import CaseService, EmbeddingService
from backend.features.calculator import MarketFeatureCalculator
from backend.opportunities.service import OpportunityFinder

log = logging.getLogger(__name__)


class M2Runtime:
    def __init__(self, pool, discovery, settings):
        self.pool, self.discovery, self.settings = pool, discovery, settings
        self.calculator = MarketFeatureCalculator(pool)
        self.analysis = FeatureExtractionService(pool, settings)
        self.embeddings = EmbeddingService(settings)
        self.cases = CaseService(pool, self.embeddings, settings.openai_embedding_model)
        self.opportunities = OpportunityFinder(pool, self.cases, settings)
        self.scheduler = AsyncIOScheduler(timezone="UTC")
        self.running = set()
        self.stopping = False
        self.catalog_lock = asyncio.Lock()
        self.catalog = {}
        self.catalog_at = None

    async def instruments(self):
        async with self.catalog_lock:
            now = datetime.now(timezone.utc)
            if (
                self.catalog_at
                and (now - self.catalog_at).total_seconds()
                < self.settings.instrument_refresh_seconds
            ):
                return self.catalog
            symbols = await self.discovery.discover_instruments()
            markets = self.discovery.exchange.markets.values()
            self.catalog = {
                m["id"]: float(m["contractSize"])
                for m in markets
                if m["id"] in symbols and m.get("contractSize")
            }
            self.catalog_at = now
            return self.catalog

    async def _job(self, name, callback):
        if self.stopping:
            return
        task = asyncio.current_task()
        self.running.add(task)
        try:
            # Transaction advisory locks release on cancellation/connection failure.
            # Separate job keys permit a scan and a feature tick to run together.
            async with self.pool.acquire() as db:
                async with db.transaction():
                    key = 420210 if name == "features" else 420211
                    if not await db.fetchval(
                        "SELECT pg_try_advisory_xact_lock($1)", key
                    ):
                        return
                    await callback()
        finally:
            self.running.discard(task)

    async def feature_tick(self):
        async def calculate():
            # Delay one full minute for collector flush and late arrivals.
            minute = datetime.now(timezone.utc).replace(
                second=0, microsecond=0
            ) - timedelta(minutes=2)
            semaphore = asyncio.Semaphore(self.settings.feature_concurrency)

            async def one(symbol, size):
                async with semaphore:
                    try:
                        await self.calculator.calculate(symbol, minute, size)
                    except Exception:
                        log.exception("Feature calculation failed for %s", symbol)

            await asyncio.gather(
                *(one(s, size) for s, size in (await self.instruments()).items())
            )

        await self._job("features", calculate)

    async def opportunity_tick(self):
        async def scan():
            if not self.embeddings.configured():
                return
            # Sequential requests bound external API cost/rate, with
            # per-symbol isolation.
            for symbol in await self.instruments():
                try:
                    await self.opportunities.scan_symbol(symbol)
                except Exception:
                    log.exception("Opportunity scan failed for %s", symbol)

        await self._job("opportunities", scan)

    def start(self):
        self.analysis.start()
        if self.settings.m2_scheduler_enabled:
            for identifier, callback, minutes in [
                ("features", self.feature_tick, 1),
                ("opportunities", self.opportunity_tick, 5),
            ]:
                self.scheduler.add_job(
                    callback,
                    "cron",
                    minute=f"*/{minutes}",
                    second=10,
                    id=identifier,
                    max_instances=1,
                    coalesce=True,
                    misfire_grace_time=30,
                )
            self.scheduler.start()

    async def close(self):
        self.stopping = True
        if self.scheduler.running:
            self.scheduler.pause()
        for task in list(self.running):
            task.cancel()
        await asyncio.gather(*list(self.running), return_exceptions=True)
        if self.scheduler.running:
            self.scheduler.shutdown(wait=False)
        await self.analysis.close()
        await self.embeddings.close()
