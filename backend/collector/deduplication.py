"""Time-bucketed dedup with explicit commit and rollback."""

import asyncio
import hashlib
import time
from collections import defaultdict

from backend.config.settings import Settings
from backend.storage.redis_client import RedisClient


class DeduplicationEngine:
    """Track in-flight and committed identities without losing failed writes.

    Buckets derive from event time, so reconnect replays retain their identity
    across wall-clock bucket boundaries. Database unique keys are the final
    cross-process guard; Redis is only a cache and may evict keys.
    """

    def __init__(self, settings: Settings, redis: RedisClient | None = None):
        self.settings = settings
        if settings.dedup_mode == "dual" and redis is None:
            raise ValueError("dual mode requires Redis")
        self.redis = redis
        self.committed: dict[str, float] = {}
        self.pending: set[str] = set()
        self.lock = asyncio.Lock()
        self.counts: dict[str, int] = defaultdict(int)
        self.next_cleanup = 0.0

    def cache_key(self, kind: str, key: str, event_time: float) -> str:
        """Hash an event identity inside its stable 60 minute bucket."""
        bucket = int(event_time // self.settings.dedup_bucket_seconds)
        digest = hashlib.sha256(key.encode()).hexdigest()
        return f"dedup:{kind}:{bucket}:{digest}"

    async def reserve(self, kind: str, key: str, event_time: float) -> str | None:
        """Atomically reserve locally; return None for a duplicate."""
        token = self.cache_key(kind, key, event_time)
        async with self.lock:
            now = time.monotonic()
            if now >= self.next_cleanup:
                self.committed = {
                    k: expiry for k, expiry in self.committed.items() if expiry > now
                }
                self.next_cleanup = now + 60
            self.counts["received"] += 1
            if token in self.pending or self.committed.get(token, 0) > now:
                self.counts["memory_hits"] += 1
                return None
            if self.settings.dedup_mode == "dual":
                if await self.redis.seen(token):
                    self.counts["redis_hits"] += 1
                    self.committed[token] = now + self.settings.dedup_ttl_seconds
                    return None
            self.pending.add(token)
            return token

    async def commit(self, token: str) -> None:
        """Publish a dedup marker only after persistence succeeded."""
        if self.settings.dedup_mode == "dual":
            await self.redis.mark_seen(token, self.settings.dedup_ttl_seconds)
        async with self.lock:
            self.pending.discard(token)
            self.committed[token] = time.monotonic() + self.settings.dedup_ttl_seconds
            self.counts["accepted"] += 1

    async def rollback(self, token: str) -> None:
        """Release an uncommitted identity so a replay can retry it."""
        async with self.lock:
            self.pending.discard(token)

    def statistics(self) -> dict[str, float]:
        """Expose memory/Redis hits and overall duplicate rate."""
        received = self.counts["received"]
        hits = self.counts["memory_hits"] + self.counts["redis_hits"]
        return {
            **self.counts,
            "duplicates": hits,
            "dedup_rate": hits / received if received else 0,
            "hit_rate": hits / received if received else 0,
            "pending": len(self.pending),
        }
