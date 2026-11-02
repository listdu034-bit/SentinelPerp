"""Shared bounded retry policy for transient I/O failures."""

import asyncpg
from redis.exceptions import RedisError
from tenacity import (
    AsyncRetrying,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from backend.config.settings import Settings

TRANSIENT_ERRORS = (
    OSError,
    TimeoutError,
    ConnectionError,
    RedisError,
    asyncpg.PostgresConnectionError,
    asyncpg.CannotConnectNowError,
    asyncpg.SerializationError,
    asyncpg.DeadlockDetectedError,
)


def io_retry(settings: Settings) -> AsyncRetrying:
    """Retry transient failures only; validation/schema errors fail immediately."""
    return AsyncRetrying(
        retry=retry_if_exception_type(TRANSIENT_ERRORS),
        stop=stop_after_attempt(settings.write_retry_attempts),
        wait=wait_exponential(multiplier=0.1, max=settings.retry_max_seconds),
        reraise=True,
    )
