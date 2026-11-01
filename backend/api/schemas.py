"""Public response types; numeric market values serialize as JSON numbers."""

import json
from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, field_validator


class EventResponse(BaseModel):
    time: datetime
    symbol: str
    exchange: str = "OKX"


class TradeResponse(EventResponse):
    trade_id: str
    trade_count: int
    price: float
    quantity: float
    side: Literal["buy", "sell"]
    receipt_timestamp: datetime


class CandleResponse(EventResponse):
    interval: str
    open: float
    high: float
    low: float
    close: float
    volume: float


class FundingRateResponse(EventResponse):
    funding_rate: float
    next_funding_time: datetime | None = None


class OpenInterestResponse(EventResponse):
    open_interest: float


class LiquidationResponse(EventResponse):
    liquidation_id: str
    side: Literal["buy", "sell"]
    price: float
    quantity: float


class QualityLogResponse(EventResponse):
    event_id: UUID
    data_type: str
    issue_type: str
    severity: Literal["warning", "error"]
    details: dict[str, Any]

    @field_validator("details", mode="before")
    @classmethod
    def decode_details(cls, value):
        return json.loads(value) if isinstance(value, str) else value


class InstrumentResponse(EventResponse):
    """Active instrument catalog; time is catalog refresh time."""


class SystemStatusResponse(BaseModel):
    time: datetime
    collection: dict[str, dict[str, Any]]
    redis: dict[str, Any]
    database: dict[str, Any]
    quality_score: float
    quality_window: str = "24h"
