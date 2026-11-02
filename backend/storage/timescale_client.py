"""TimescaleDB pooling and bounded, retryable batches."""

import asyncio
import json
from collections import defaultdict
from contextlib import asynccontextmanager
from datetime import datetime
from typing import AsyncIterator

import asyncpg
from pydantic import BaseModel

from backend.config.settings import Settings
from backend.storage.models import EVENT_TABLES
from backend.utils.retry import io_retry


class TimescaleClient:
    """Batch at 100 rows or one second, retaining failed batches for retry.

    submit() returns a durability future. Callers acknowledge dedup only after
    that future completes. The queue is bounded to apply backpressure.
    """

    def __init__(self, settings: Settings):
        self.settings = settings
        self.pool: asyncpg.Pool | None = None
        self.queue: asyncio.Queue = asyncio.Queue(settings.buffer_max_size)
        self.worker: asyncio.Task | None = None
        self.accepting = False

    async def connect(self) -> None:
        """Open the pool and start the single batch writer."""
        async for attempt in io_retry(self.settings):
            with attempt:
                self.pool = await asyncpg.create_pool(
                    self.settings.database_url.get_secret_value(),
                    min_size=self.settings.db_pool_min_size,
                    max_size=self.settings.db_pool_size,
                    command_timeout=self.settings.db_command_timeout,
                )
        self.accepting = True
        self.worker = asyncio.create_task(self._writer(), name="db-writer")

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[asyncpg.Connection]:
        """Expose an acquired connection within an atomic transaction."""
        if self.pool is None:
            raise RuntimeError("Database is not connected")
        async with self.pool.acquire() as connection:
            async with connection.transaction():
                yield connection

    async def insert_batch(self, events: list[BaseModel]) -> None:
        """Insert a heterogeneous batch atomically and idempotently."""
        groups: dict[type, list] = defaultdict(list)
        for event in events:
            if type(event) not in EVENT_TABLES:
                raise ValueError("Unsupported event model")
            groups[type(event)].append(event)
        async for attempt in io_retry(self.settings):
            with attempt:
                async with self.transaction() as connection:
                    for model, rows in groups.items():
                        columns = list(model.model_fields)
                        placeholders = ", ".join(
                            f"${i}" for i in range(1, len(columns) + 1)
                        )
                        sql = (
                            f"INSERT INTO {EVENT_TABLES[model]} "
                            f"({', '.join(chr(34) + c + chr(34) for c in columns)}) "
                            f"VALUES ({placeholders}) ON CONFLICT DO NOTHING"
                        )
                        values = []
                        for row in rows:
                            data = row.model_dump()
                            values.append(
                                tuple(
                                    json.dumps(row.model_dump(mode="json")[c])
                                    if isinstance(data[c], (dict, list))
                                    else data[c]
                                    for c in columns
                                )
                            )
                        await connection.executemany(sql, values)

    async def submit(self, event: BaseModel) -> asyncio.Future:
        """Enqueue an event; return a future completed after commit."""
        if not self.accepting or self.worker is None:
            raise RuntimeError("Database writer is not running")
        if self.worker.done():
            await self.worker  # propagate the actual failure
            raise RuntimeError("Database writer stopped")
        future = asyncio.get_running_loop().create_future()
        # Surface failures even if the submitting callback is cancelled.
        future.add_done_callback(
            lambda done: done.exception() if not done.cancelled() else None
        )
        enqueue = asyncio.create_task(self.queue.put((event, future)))
        try:
            await asyncio.wait(
                [enqueue, self.worker], return_when=asyncio.FIRST_COMPLETED
            )
            if self.worker.done():
                if not enqueue.done():
                    enqueue.cancel()
                await asyncio.gather(enqueue, return_exceptions=True)
                await self.worker
                raise RuntimeError("Database writer stopped during admission")
            await enqueue
        except BaseException:
            if not enqueue.done():
                enqueue.cancel()
                await asyncio.gather(enqueue, return_exceptions=True)
            raise
        return future

    async def store(self, event: BaseModel) -> None:
        """Wait until an event is durably committed."""
        await asyncio.shield(await self.submit(event))

    async def _writer(self) -> None:
        batch = []
        try:
            while True:
                item = await self.queue.get()
                if item is None:
                    self.queue.task_done()
                    break
                batch.append(item)
                deadline = asyncio.get_running_loop().time() + (
                    self.settings.batch_flush_seconds
                )
                stopping = False
                while len(batch) < self.settings.batch_size:
                    remaining = deadline - asyncio.get_running_loop().time()
                    if remaining <= 0:
                        break
                    try:
                        item = await asyncio.wait_for(self.queue.get(), remaining)
                    except TimeoutError:
                        break
                    if item is None:
                        self.queue.task_done()
                        stopping = True
                        break
                    batch.append(item)
                await self.insert_batch([row for row, _ in batch])
                for _, future in batch:
                    if not future.done():
                        future.set_result(None)
                    self.queue.task_done()
                batch = []
                if stopping:
                    break
        except BaseException as error:
            for _, future in batch:
                if not future.done():
                    future.set_exception(error)
                self.queue.task_done()
            while not self.queue.empty():
                item = self.queue.get_nowait()
                if item is not None and not item[1].done():
                    item[1].set_exception(error)
                self.queue.task_done()
            self.accepting = False
            raise

    async def query(
        self,
        table: str,
        symbol: str,
        start: datetime,
        end: datetime,
        limit: int = 1000,
    ) -> list[dict]:
        """Query a whitelisted table over a half-open UTC time range."""
        if table not in EVENT_TABLES.values():
            raise ValueError("Unsupported table")
        if not 1 <= limit <= 10000 or start >= end:
            raise ValueError("Invalid range or limit")
        if start.tzinfo is None or end.tzinfo is None:
            raise ValueError("Time bounds must have time zones")
        async with self.transaction() as connection:
            rows = await connection.fetch(
                f"SELECT * FROM {table} WHERE symbol=$1 "
                "AND time >= $2 AND time < $3 ORDER BY time LIMIT $4",
                symbol,
                start,
                end,
                limit,
            )
        return [dict(row) for row in rows]

    async def close(self) -> None:
        """Stop admission, flush pending rows, then release the pool."""
        self.accepting = False
        try:
            if self.worker is not None:
                if not self.worker.done():
                    await self.queue.put(None)
                await self.worker
        finally:
            if self.pool is not None:
                await self.pool.close()
                self.pool = None
