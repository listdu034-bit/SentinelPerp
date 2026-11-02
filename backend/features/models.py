"""L4 minute feature contract. Missing observations remain null."""

from typing import Annotated

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

Score = Annotated[float, Field(ge=0, le=1)]


class MarketFeature1Min(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False, extra="forbid")

    time: AwareDatetime
    symbol: str = Field(pattern=r"^[A-Z0-9]+-USDT-SWAP$")
    price_open: float | None = None
    price_high: float | None = None
    price_low: float | None = None
    price_close: float | None = None
    volume: float | None = None
    volume_usd: float | None = None
    price_change_pct: float | None = None
    volatility: float | None = None
    amplitude_pct: float | None = None
    buy_volume_usd: float | None = None
    sell_volume_usd: float | None = None
    delta_usd: float | None = None
    cvd: float | None = None
    trade_count: int | None = None
    buy_sell_ratio: float | None = None
    avg_trade_size_usd: float | None = None
    oi: float | None = None
    oi_usd: float | None = None
    oi_delta: float | None = None
    oi_change_pct: float | None = None
    oi_volume_ratio: float | None = None
    oi_direction: str | None = None
    funding_rate: float | None = None
    funding_trend: float | None = None
    bid_depth_10: float | None = None
    ask_depth_10: float | None = None
    obi: Annotated[float | None, Field(ge=-1, le=1)] = None
    spread_bps: float | None = None
    long_liq_usd: float | None = None
    short_liq_usd: float | None = None
    liq_count: int | None = None
    liq_imbalance: Annotated[float | None, Field(ge=-1, le=1)] = None
    liquidation_intensity: float | None = None
    liquidation_long_short_ratio: float | None = None
    coverage: Score
    quality: Score
    age_seconds: int = Field(ge=0)
    source_flags: int = Field(ge=0)
    is_final: bool = False
    revision_count: int = 0
