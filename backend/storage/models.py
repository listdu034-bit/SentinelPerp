"""Normalized UTC models; quantities are OKX contract units, not base coins."""

from datetime import datetime
from decimal import Decimal
from typing import Annotated, Any, Literal
from uuid import UUID, uuid4

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    model_validator,
)

Positive = Annotated[Decimal, Field(gt=0, allow_inf_nan=False)]
NonNegative = Annotated[Decimal, Field(ge=0, allow_inf_nan=False)]
Finite = Annotated[Decimal, Field(allow_inf_nan=False)]


class MarketEvent(BaseModel):
    """Shared event identity and provenance."""

    model_config = ConfigDict(extra="forbid")
    time: AwareDatetime
    exchange: Literal["OKX"] = "OKX"
    symbol: str = Field(pattern=r"^.+-USDT-SWAP$")
    receipt_timestamp: AwareDatetime


class Trade(MarketEvent):
    """An executed trade in contract units."""

    trade_id: str = Field(min_length=1)
    trade_count: int = Field(1, gt=0)
    price: Positive
    quantity: Positive
    side: Literal["buy", "sell"]


class Candle(MarketEvent):
    """A closed OHLCV candle."""

    interval: str = "1m"
    open: Positive
    high: Positive
    low: Positive
    close: Positive
    volume: NonNegative

    @model_validator(mode="after")
    def validate_ohlc(self) -> "Candle":
        """Ensure OHLC prices describe a possible candle."""
        if (
            not self.low
            <= min(self.open, self.close)
            <= max(self.open, self.close)
            <= self.high
        ):
            raise ValueError("inconsistent OHLC prices")
        return self


class FundingRate(MarketEvent):
    """Current funding observation and optional settlement time."""

    funding_rate: Finite
    next_funding_time: AwareDatetime | None = None


class OpenInterest(MarketEvent):
    """Outstanding contracts."""

    open_interest: NonNegative


class Liquidation(MarketEvent):
    """Exchange liquidation observation (side is executed buy/sell)."""

    liquidation_id: str = Field(min_length=1)
    side: Literal["buy", "sell"]
    quantity: Positive
    price: Positive


class OrderBookSnapshot(MarketEvent):
    """Reconstructed L2 levels, sorted best price first."""

    bids: list[tuple[Positive, Positive]]
    asks: list[tuple[Positive, Positive]]

    @model_validator(mode="after")
    def validate_book(self) -> "OrderBookSnapshot":
        """Reject empty, crossed, unsorted or duplicate price levels."""
        if not self.bids or not self.asks:
            raise ValueError("both book sides are required")
        bids = [level[0] for level in self.bids]
        asks = [level[0] for level in self.asks]
        if bids != sorted(set(bids), reverse=True) or asks != sorted(set(asks)):
            raise ValueError("book levels must be unique and sorted")
        if bids[0] >= asks[0]:
            raise ValueError("crossed order book")
        return self


class QualityLog(BaseModel):
    """A persisted data quality incident."""

    time: AwareDatetime
    event_id: UUID = Field(default_factory=uuid4)
    data_type: str
    symbol: str
    issue_type: str
    severity: Literal["warning", "error"] = "warning"
    details: dict[str, Any] = Field(default_factory=dict)


EVENT_TABLES = {
    Trade: "trades",
    Candle: "candles",
    FundingRate: "funding_rates",
    OpenInterest: "open_interest",
    Liquidation: "liquidations",
    OrderBookSnapshot: "orderbook_snapshots",
    QualityLog: "quality_logs",
}


def utc_timestamp(value: float) -> datetime:
    """Convert Cryptofeed seconds since epoch to an aware UTC datetime."""
    from datetime import timezone

    return datetime.fromtimestamp(float(value), timezone.utc)
