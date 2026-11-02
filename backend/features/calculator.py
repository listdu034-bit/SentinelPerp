"""Compute closed-minute features using bounded source queries and contract units."""

import json
from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd

from backend.features.models import MarketFeature1Min


def ratio(numerator, denominator):
    """Undefined ratios are null, never infinity or an invented neutral value."""
    return numerator / denominator if denominator else None


def calculate_features(symbol, minute, sources, contract_size):
    """Pure formulas. CVD resets at UTC midnight; volatility is 60m log-return SD.

    Source bits: candles, trades, OI, funding, book, liquidations, spot (M1 absent).
    An empty liquidation window cannot prove feed health and gets no coverage bit.
    """
    end = minute + timedelta(minutes=1)
    candles = sources["candles"]
    current = [c for c in candles if c["time"] == minute]
    candle = current[-1] if current else None
    trade, oi, funding, book, liq = (
        sources.get(key) for key in ("trades", "oi", "funding", "book", "liquidations")
    )
    flags = sum(
        1 << i
        for i, valid in enumerate(
            [
                candle is not None,
                bool(trade and trade["trade_count"]),
                bool(oi),
                bool(funding),
                bool(book),
                bool(liq and liq["liq_count"]),
            ]
        )
        if valid
    )
    observed = [trade, oi, funding, book, liq]
    # Candles are timestamped at open, but describe observations through close.
    if candle:
        observed.append(dict(time=candle["time"] + timedelta(minutes=1)))
    # Funding is sampled rather than traded; its separate bounded lookback is 9h.
    ages = [
        max(0, int((end - row["time"]).total_seconds()))
        for row in observed
        if row and row.get("time")
    ]
    age = max(ages, default=600)
    coverage = flags.bit_count() / 7
    freshness = 1.0 if age < 60 else 0.8 if age < 300 else 0.5 if age < 600 else 0.2
    values = dict(
        time=minute,
        symbol=symbol,
        source_flags=flags,
        coverage=coverage,
        age_seconds=age,
        quality=coverage * 0.5
        + freshness * 0.3
        + (0.0 if sources.get("has_anomalies") else 0.2),
    )
    size = float(contract_size)
    if size <= 0 or not np.isfinite(size):
        raise ValueError("A positive linear contract size is required")
    price = float(candle["close"]) if candle else None
    if candle:
        opening, high, low = (float(candle[k]) for k in ("open", "high", "low"))
        frame = pd.DataFrame(candles).sort_values("time")
        closes = frame["close"].astype(float)
        contiguous = frame["time"].diff().iloc[1:] == timedelta(minutes=1)
        returns = np.log(closes).diff().dropna()
        values.update(
            price_open=opening,
            price_high=high,
            price_low=low,
            price_close=price,
            volume=float(candle["volume"]),
            price_change_pct=(price / opening - 1) * 100,
            amplitude_pct=(high - low) / opening * 100,
            volatility=float(returns.std(ddof=0)) * 100
            if len(returns) >= 2 and contiguous.all()
            else None,
        )
    if trade and trade["trade_count"]:
        buy, sell = (
            float(trade["buy_notional"]) * size,
            float(trade["sell_notional"]) * size,
        )
        values.update(
            buy_volume_usd=buy,
            sell_volume_usd=sell,
            delta_usd=buy - sell,
            volume_usd=buy + sell,
            cvd=float(sources["cvd"]) * size,
            trade_count=trade["trade_count"],
            buy_sell_ratio=ratio(buy, sell),
            avg_trade_size_usd=ratio(buy + sell, trade["trade_count"]),
        )
    if oi:
        interest = float(oi["open_interest"])
        previous = sources.get("previous_oi")
        delta = interest - float(previous["open_interest"]) if previous else None
        change = (
            ratio(delta * 100, float(previous["open_interest"])) if previous else None
        )
        direction = None
        move = values.get("price_change_pct")
        if delta is not None and move is not None:
            direction = (
                "neutral"
                if delta == 0 or move == 0
                else "long_build"
                if delta > 0 and move > 0
                else "short_build"
                if delta > 0
                else "short_unwind"
                if move > 0
                else "long_unwind"
            )
        values.update(
            oi=interest,
            oi_usd=interest * size * price if price else None,
            oi_delta=delta,
            oi_change_pct=change,
            oi_direction=direction,
            oi_volume_ratio=ratio(interest, values.get("volume")),
        )
    if funding:
        rate = float(funding["funding_rate"])
        prior = sources.get("previous_funding")
        values.update(
            funding_rate=rate,
            funding_trend=rate - float(prior["funding_rate"]) if prior else None,
        )
    if book:
        bids, asks = (
            json.loads(book[k]) if isinstance(book[k], str) else book[k]
            for k in ("bids", "asks")
        )
        bid = sum(float(p) * float(q) * size for p, q in bids[:10])
        ask = sum(float(p) * float(q) * size for p, q in asks[:10])
        best_bid, best_ask = float(bids[0][0]), float(asks[0][0])
        values.update(
            bid_depth_10=bid,
            ask_depth_10=ask,
            obi=ratio(bid - ask, bid + ask),
            spread_bps=(best_ask - best_bid) / ((best_ask + best_bid) / 2) * 10000,
        )
    if liq and liq["liq_count"]:
        long, short = (
            float(liq["long_notional"]) * size,
            float(liq["short_notional"]) * size,
        )
        values.update(
            long_liq_usd=long,
            short_liq_usd=short,
            liq_count=liq["liq_count"],
            liq_imbalance=ratio(short - long, short + long),
            liquidation_intensity=ratio(long + short, values.get("volume_usd")),
            liquidation_long_short_ratio=ratio(long, short),
        )
    return MarketFeature1Min(**values)


class MarketFeatureCalculator:
    def __init__(self, pool):
        self.pool = pool

    async def calculate(self, symbol, minute, contract_size):
        if minute.tzinfo is None or minute.second or minute.microsecond:
            raise ValueError("Minute must be aligned and timezone aware")
        minute = minute.astimezone(timezone.utc)
        end = minute + timedelta(minutes=1)
        if end > datetime.now(timezone.utc):
            raise ValueError("Only closed minutes can be calculated")
        async with self.pool.acquire() as db:
            async with db.transaction(isolation="repeatable_read"):
                candles = await db.fetch(
                    "SELECT * FROM candles WHERE symbol=$1 AND interval='1m' "
                    "AND time >= $2 AND time < $3 ORDER BY time",
                    symbol,
                    minute - timedelta(minutes=59),
                    end,
                )
                trades = await db.fetchrow(
                    "SELECT max(time) AS time, coalesce(sum(trade_count),0)::bigint "
                    "AS trade_count, "
                    "coalesce(sum(price*quantity) FILTER (WHERE side='buy'),0) AS "
                    "buy_notional, "
                    "coalesce(sum(price*quantity) FILTER (WHERE side='sell'),0) AS "
                    "sell_notional "
                    "FROM trades WHERE symbol=$1 AND time >= $2 AND time < $3",
                    symbol,
                    minute,
                    end,
                )
                cvd = await db.fetchval(
                    "SELECT coalesce(sum(CASE WHEN side='buy' THEN price*quantity "
                    "ELSE -price*quantity END),0) FROM trades "
                    "WHERE symbol=$1 AND time >= $2 AND time < $3",
                    symbol,
                    minute.replace(hour=0, minute=0),
                    end,
                )
                sources = dict(
                    candles=[dict(c) for c in candles], trades=dict(trades), cvd=cvd
                )
                for key, table, lookback in [
                    ("oi", "open_interest", timedelta(minutes=5)),
                    ("funding", "funding_rates", timedelta(hours=9)),
                    ("book", "orderbook_snapshots", timedelta(minutes=2)),
                ]:
                    rows = await db.fetch(
                        f"SELECT * FROM {table} WHERE symbol=$1 AND time >= $2 "
                        "AND time < $3 ORDER BY time DESC LIMIT 2",
                        symbol,
                        end - lookback,
                        end,
                    )
                    sources[key] = dict(rows[0]) if rows else None
                    if key == "oi":
                        sources["previous_oi"] = await db.fetchrow(
                            "SELECT * FROM open_interest "
                            "WHERE symbol=$1 AND time >= $2 "
                            "AND time < $3 ORDER BY time DESC LIMIT 1",
                            symbol,
                            minute - timedelta(minutes=5),
                            minute,
                        )
                    elif key == "funding":
                        sources["previous_funding"] = (
                            dict(rows[1]) if len(rows) > 1 else None
                        )
                sources["liquidations"] = dict(
                    await db.fetchrow(
                        "SELECT max(time) AS time, count(*)::int AS liq_count, "
                        "coalesce(sum(price*quantity) FILTER (WHERE side='sell'),0) AS "
                        "long_notional, "
                        "coalesce(sum(price*quantity) FILTER (WHERE side='buy'),0) AS "
                        "short_notional "
                        "FROM liquidations WHERE symbol=$1 "
                        "AND time >= $2 AND time < $3",
                        symbol,
                        minute,
                        end,
                    )
                )
                sources["has_anomalies"] = await db.fetchval(
                    "SELECT EXISTS(SELECT 1 FROM quality_logs WHERE symbol=$1 "
                    "AND time >= $2 AND time < $3 AND severity='error')",
                    symbol,
                    minute,
                    end,
                )
                feature = calculate_features(symbol, minute, sources, contract_size)
                data = feature.model_dump()
                columns = list(data)
                updates = ", ".join(
                    f"{c}=EXCLUDED.{c}"
                    for c in columns
                    if c not in {"time", "symbol", "revision_count"}
                )
                await db.execute(
                    f"INSERT INTO market_features_1m ({', '.join(columns)}) VALUES "
                    f"({', '.join(f'${i + 1}' for i in range(len(columns)))}) "
                    f"ON CONFLICT (time,symbol) DO UPDATE SET {updates}, "
                    "revision_count=market_features_1m.revision_count+1",
                    *data.values(),
                )
        return feature
