"""Redis connection pool, latest market state, and dedup primitives."""

import json
from typing import Any

from redis.asyncio import Redis

from backend.config.settings import Settings
from backend.storage.models import MarketEvent
from backend.utils.retry import io_retry

# Prevent delayed/replayed events from moving the latest state backwards.
LATEST_SCRIPT = """
local old = redis.call('GET', KEYS[1])
if old then
    local previous = cjson.decode(old)
    if previous.time > ARGV[1] then return 0 end
end
redis.call('SET', KEYS[1], ARGV[2], 'EX', ARGV[3])
redis.call('PUBLISH', ARGV[4], ARGV[2])
return 1
"""


class RedisClient:
    """Async Redis operations, with TTLs on every cache key."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self.client: Redis | None = None

    async def connect(self) -> None:
        """Create a bounded connection pool and verify connectivity."""
        self.client = Redis.from_url(
            self.settings.redis_url.get_secret_value(),
            max_connections=self.settings.redis_max_connections,
            decode_responses=True,
            socket_timeout=10,
            socket_connect_timeout=10,
        )
        async for attempt in io_retry(self.settings):
            with attempt:
                await self.client.ping()

    def connection(self) -> Redis:
        """Return the initialized client."""
        if self.client is None:
            raise RuntimeError("Redis is not connected")
        return self.client

    async def close(self) -> None:
        """Close the client and its owned connection pool."""
        if self.client is not None:
            await self.client.aclose()
            self.client = None

    async def set_latest(self, kind: str, event: MarketEvent) -> None:
        """Store latest state only when its event time is newer."""
        # Fixed width UTC text supports ordering in the Lua script.
        from datetime import timezone

        payload = event.model_dump(mode="json")
        payload["time"] = event.time.astimezone(timezone.utc).isoformat(
            timespec="microseconds"
        )
        async for attempt in io_retry(self.settings):
            with attempt:
                await self.connection().eval(
                    LATEST_SCRIPT,
                    1,
                    f"latest:{kind}:{event.symbol}",
                    payload["time"],
                    json.dumps(payload),
                    self.settings.redis_latest_ttl,
                    f"events:{kind}:{event.symbol}",
                )

    async def get_latest(self, kind: str, symbol: str) -> dict | None:
        """Read the latest normalized market event."""
        value = await self.connection().get(f"latest:{kind}:{symbol}")
        return json.loads(value) if value else None

    async def seen(self, key: str) -> bool:
        """Check a dedup marker without refreshing its TTL."""
        async for attempt in io_retry(self.settings):
            with attempt:
                return bool(await self.connection().exists(key))
        return False

    async def mark_seen(self, key: str, ttl: int) -> None:
        """Mark only a successfully persisted event as seen."""
        async for attempt in io_retry(self.settings):
            with attempt:
                await self.connection().set(key, "1", ex=ttl)

    async def set_quality(self, symbol: str, metrics: dict[str, Any]) -> None:
        """Cache current quality counters with a bounded lifetime."""
        async for attempt in io_retry(self.settings):
            with attempt:
                await self.connection().set(
                    f"quality:{symbol}",
                    json.dumps(metrics),
                    ex=self.settings.redis_quality_ttl,
                )
