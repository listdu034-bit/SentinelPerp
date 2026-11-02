"""Validated environment configuration for the collector."""

from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """All runtime tuning knobs; names map directly to environment variables."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    api_cors_origins: list[str] = [
        "http://localhost:3000",
        "http://localhost:5173",  # Vite dev server
        "http://localhost:8080",  # Alternative frontend port
    ]
    m2_scheduler_enabled: bool = True
    feature_concurrency: int = Field(4, ge=1, le=32)
    analysis_concurrency: int = Field(2, ge=1, le=16)
    analysis_queue_size: int = Field(100, ge=1, le=1000)
    ai_timeout_seconds: float = Field(120, gt=0, le=600)
    openai_api_key: SecretStr = SecretStr("")
    openai_analysis_model: str = "gpt-4o-mini"
    openai_embedding_model: str = "text-embedding-3-small"
    opportunity_min_quality: float = Field(0.7, ge=0, le=1)
    opportunity_min_similarity: float = Field(0.8, ge=0, le=1)
    log_level: str = "INFO"
    okx_market_filter: str = "*-USDT-SWAP"
    okx_rest_url: str = "https://www.okx.com"
    instrument_refresh_seconds: float = Field(300, gt=0)
    redis_url: SecretStr = SecretStr("redis://localhost:6379/0")
    redis_max_connections: int = Field(50, gt=0)
    redis_latest_ttl: int = Field(3600, gt=0)
    redis_quality_ttl: int = Field(86400, gt=0)
    database_url: SecretStr = SecretStr(
        "postgresql://sentinel@localhost:5432/sentinelperp"
    )
    db_pool_min_size: int = Field(2, gt=0)
    db_pool_size: int = Field(20, gt=0)
    db_command_timeout: float = Field(30, gt=0)
    batch_size: int = Field(100, gt=0)
    batch_flush_seconds: float = Field(1, gt=0)
    buffer_max_size: int = Field(10000, gt=0)
    write_retry_attempts: int = Field(5, gt=0)
    retry_max_seconds: float = Field(10, gt=0)
    dedup_mode: Literal["memory", "dual"] = "dual"
    dedup_bucket_seconds: int = Field(3600, gt=0)
    dedup_ttl_seconds: int = Field(86400, gt=0)
    trade_max_latency_ms: float = Field(5000, ge=0)
    out_of_order_tolerance_ms: float = Field(2000, ge=0)
    trade_stale_seconds: float = Field(15, gt=0)
    quality_check_seconds: float = Field(5, gt=0)
    trade_id_gap_detection: bool = True
    orderbook_depth: int = Field(20, gt=0)
    orderbook_snapshot_seconds: float = Field(60, gt=0)
    feed_timeout_seconds: int = Field(30, gt=0)
    feed_reconnect_seconds: float = Field(5, gt=0)

    @model_validator(mode="after")
    def validate_limits(self) -> "Settings":
        """Reject contradictory pool and buffer limits at startup."""
        if self.m2_scheduler_enabled and self.db_pool_size < 3:
            raise ValueError("M2 scheduler requires db_pool_size >= 3")
        if self.db_pool_min_size > self.db_pool_size:
            raise ValueError("db_pool_min_size exceeds db_pool_size")
        if self.buffer_max_size < self.batch_size:
            raise ValueError("buffer_max_size must be >= batch_size")
        return self


@lru_cache
def get_settings() -> Settings:
    """Load settings once per process."""
    return Settings()
