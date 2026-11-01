-- P0 only. L4 feature schemas/calculators are delivered in M1 phase 2.
-- All unique constraints include the hypertable partition column.
CREATE EXTENSION IF NOT EXISTS timescaledb;

CREATE TABLE IF NOT EXISTS trades (
    time TIMESTAMPTZ NOT NULL,
    exchange TEXT NOT NULL DEFAULT 'OKX',
    symbol TEXT NOT NULL,
    receipt_timestamp TIMESTAMPTZ NOT NULL,
    trade_id TEXT NOT NULL, trade_count INTEGER NOT NULL DEFAULT 1 CHECK (trade_count > 0), price NUMERIC NOT NULL CHECK (price > 0), quantity NUMERIC NOT NULL CHECK (quantity > 0), side TEXT NOT NULL CHECK (side IN ('buy','sell')), PRIMARY KEY (time, exchange, symbol, trade_id)
);

CREATE TABLE IF NOT EXISTS candles (
    time TIMESTAMPTZ NOT NULL,
    exchange TEXT NOT NULL DEFAULT 'OKX',
    symbol TEXT NOT NULL,
    receipt_timestamp TIMESTAMPTZ NOT NULL,
    interval TEXT NOT NULL, open NUMERIC NOT NULL CHECK (open > 0), high NUMERIC NOT NULL, low NUMERIC NOT NULL CHECK (low > 0), close NUMERIC NOT NULL CHECK (close > 0), volume NUMERIC NOT NULL CHECK (volume >= 0), CHECK (low <= LEAST(open,close) AND high >= GREATEST(open,close)), PRIMARY KEY (time, exchange, symbol, interval)
);

CREATE TABLE IF NOT EXISTS funding_rates (
    time TIMESTAMPTZ NOT NULL,
    exchange TEXT NOT NULL DEFAULT 'OKX',
    symbol TEXT NOT NULL,
    receipt_timestamp TIMESTAMPTZ NOT NULL,
    funding_rate NUMERIC NOT NULL, next_funding_time TIMESTAMPTZ, PRIMARY KEY (time, exchange, symbol)
);

CREATE TABLE IF NOT EXISTS open_interest (
    time TIMESTAMPTZ NOT NULL,
    exchange TEXT NOT NULL DEFAULT 'OKX',
    symbol TEXT NOT NULL,
    receipt_timestamp TIMESTAMPTZ NOT NULL,
    open_interest NUMERIC NOT NULL CHECK (open_interest >= 0), PRIMARY KEY (time, exchange, symbol)
);

CREATE TABLE IF NOT EXISTS liquidations (
    time TIMESTAMPTZ NOT NULL,
    exchange TEXT NOT NULL DEFAULT 'OKX',
    symbol TEXT NOT NULL,
    receipt_timestamp TIMESTAMPTZ NOT NULL,
    liquidation_id TEXT NOT NULL, side TEXT NOT NULL CHECK (side IN ('buy','sell')), quantity NUMERIC NOT NULL CHECK (quantity > 0), price NUMERIC NOT NULL CHECK (price > 0), PRIMARY KEY (time, exchange, symbol, liquidation_id)
);

CREATE TABLE IF NOT EXISTS orderbook_snapshots (
    time TIMESTAMPTZ NOT NULL,
    exchange TEXT NOT NULL DEFAULT 'OKX',
    symbol TEXT NOT NULL,
    receipt_timestamp TIMESTAMPTZ NOT NULL,
    bids JSONB NOT NULL, asks JSONB NOT NULL, PRIMARY KEY (time, exchange, symbol)
);

CREATE TABLE IF NOT EXISTS quality_logs (
    time TIMESTAMPTZ NOT NULL,
    event_id UUID NOT NULL,
    data_type TEXT NOT NULL,
    symbol TEXT NOT NULL,
    issue_type TEXT NOT NULL,
    severity TEXT NOT NULL,
    details JSONB NOT NULL,
    PRIMARY KEY (time, event_id)
);
SELECT create_hypertable('trades', 'time', chunk_time_interval => INTERVAL '1 day', if_not_exists => TRUE);
CREATE INDEX IF NOT EXISTS idx_trades_symbol_time ON trades (symbol, time DESC);
SELECT add_retention_policy('trades', INTERVAL '7 days', if_not_exists => TRUE);
SELECT create_hypertable('candles', 'time', chunk_time_interval => INTERVAL '1 day', if_not_exists => TRUE);
CREATE INDEX IF NOT EXISTS idx_candles_symbol_time ON candles (symbol, time DESC);
SELECT add_retention_policy('candles', INTERVAL '7 days', if_not_exists => TRUE);
SELECT create_hypertable('funding_rates', 'time', chunk_time_interval => INTERVAL '1 day', if_not_exists => TRUE);
CREATE INDEX IF NOT EXISTS idx_funding_rates_symbol_time ON funding_rates (symbol, time DESC);
SELECT add_retention_policy('funding_rates', INTERVAL '7 days', if_not_exists => TRUE);
SELECT create_hypertable('open_interest', 'time', chunk_time_interval => INTERVAL '1 day', if_not_exists => TRUE);
CREATE INDEX IF NOT EXISTS idx_open_interest_symbol_time ON open_interest (symbol, time DESC);
SELECT add_retention_policy('open_interest', INTERVAL '7 days', if_not_exists => TRUE);
SELECT create_hypertable('liquidations', 'time', chunk_time_interval => INTERVAL '1 day', if_not_exists => TRUE);
CREATE INDEX IF NOT EXISTS idx_liquidations_symbol_time ON liquidations (symbol, time DESC);
SELECT add_retention_policy('liquidations', INTERVAL '7 days', if_not_exists => TRUE);
SELECT create_hypertable('orderbook_snapshots', 'time', chunk_time_interval => INTERVAL '1 day', if_not_exists => TRUE);
CREATE INDEX IF NOT EXISTS idx_orderbook_snapshots_symbol_time ON orderbook_snapshots (symbol, time DESC);
SELECT add_retention_policy('orderbook_snapshots', INTERVAL '7 days', if_not_exists => TRUE);
SELECT create_hypertable('quality_logs', 'time', chunk_time_interval => INTERVAL '1 day', if_not_exists => TRUE);
CREATE INDEX IF NOT EXISTS idx_quality_logs_symbol_time ON quality_logs (symbol, time DESC);
SELECT add_retention_policy('quality_logs', INTERVAL '7 days', if_not_exists => TRUE);

-- Refresh windows stay strictly inside raw retention. Never refresh deleted
-- source ranges: doing so would erase the older materialized history.
-- Aggregate directly from raw 1m candles to avoid hierarchical refresh races.

CREATE MATERIALIZED VIEW IF NOT EXISTS candles_5m
WITH (timescaledb.continuous) AS
SELECT time_bucket(INTERVAL '5 minutes', time) AS time,
    exchange, symbol, first(open,time) AS open, max(high) AS high,
    min(low) AS low, last(close,time) AS close, sum(volume) AS volume
FROM candles WHERE interval = '1m'
GROUP BY time_bucket(INTERVAL '5 minutes', time), exchange, symbol
WITH NO DATA;
SELECT add_continuous_aggregate_policy('candles_5m',
    start_offset => INTERVAL '6 days', end_offset => INTERVAL '1 minute',
    schedule_interval => INTERVAL '5 minutes', if_not_exists => TRUE);
SELECT add_retention_policy('candles_5m', INTERVAL '60 days', if_not_exists => TRUE);
CREATE INDEX IF NOT EXISTS idx_candles_5m_symbol_time ON candles_5m (symbol, time DESC);

CREATE MATERIALIZED VIEW IF NOT EXISTS candles_1h
WITH (timescaledb.continuous) AS
SELECT time_bucket(INTERVAL '1 hour', time) AS time,
    exchange, symbol, first(open,time) AS open, max(high) AS high,
    min(low) AS low, last(close,time) AS close, sum(volume) AS volume
FROM candles WHERE interval = '1m'
GROUP BY time_bucket(INTERVAL '1 hour', time), exchange, symbol
WITH NO DATA;
SELECT add_continuous_aggregate_policy('candles_1h',
    start_offset => INTERVAL '6 days', end_offset => INTERVAL '1 minute',
    schedule_interval => INTERVAL '5 minutes', if_not_exists => TRUE);
SELECT add_retention_policy('candles_1h', INTERVAL '60 days', if_not_exists => TRUE);
CREATE INDEX IF NOT EXISTS idx_candles_1h_symbol_time ON candles_1h (symbol, time DESC);

CREATE MATERIALIZED VIEW IF NOT EXISTS candles_1d
WITH (timescaledb.continuous) AS
SELECT time_bucket(INTERVAL '1 day', time) AS time,
    exchange, symbol, first(open,time) AS open, max(high) AS high,
    min(low) AS low, last(close,time) AS close, sum(volume) AS volume
FROM candles WHERE interval = '1m'
GROUP BY time_bucket(INTERVAL '1 day', time), exchange, symbol
WITH NO DATA;
SELECT add_continuous_aggregate_policy('candles_1d',
    start_offset => INTERVAL '6 days', end_offset => INTERVAL '1 minute',
    schedule_interval => INTERVAL '5 minutes', if_not_exists => TRUE);
SELECT add_retention_policy('candles_1d', INTERVAL '60 days', if_not_exists => TRUE);
CREATE INDEX IF NOT EXISTS idx_candles_1d_symbol_time ON candles_1d (symbol, time DESC);

CREATE MATERIALIZED VIEW IF NOT EXISTS trades_hourly
WITH (timescaledb.continuous) AS
SELECT time_bucket(INTERVAL '1 hour', time) AS time,
    exchange, symbol, sum(trade_count) AS trade_count, count(*) AS message_count, sum(quantity) AS quantity,
    first(price,time) AS open, max(price) AS high, min(price) AS low,
    last(price,time) AS close,
    sum(CASE WHEN side='buy' THEN quantity ELSE 0 END) AS buy_quantity,
    sum(CASE WHEN side='sell' THEN quantity ELSE 0 END) AS sell_quantity
FROM trades 
GROUP BY time_bucket(INTERVAL '1 hour', time), exchange, symbol
WITH NO DATA;
SELECT add_continuous_aggregate_policy('trades_hourly',
    start_offset => INTERVAL '6 days', end_offset => INTERVAL '1 minute',
    schedule_interval => INTERVAL '5 minutes', if_not_exists => TRUE);
SELECT add_retention_policy('trades_hourly', INTERVAL '60 days', if_not_exists => TRUE);
CREATE INDEX IF NOT EXISTS idx_trades_hourly_symbol_time ON trades_hourly (symbol, time DESC);

CREATE MATERIALIZED VIEW IF NOT EXISTS orderbook_hourly
WITH (timescaledb.continuous) AS
SELECT time_bucket(INTERVAL '1 hour', time) AS time,
    exchange, symbol, last(bids,time) AS bids, last(asks,time) AS asks
FROM orderbook_snapshots 
GROUP BY time_bucket(INTERVAL '1 hour', time), exchange, symbol
WITH NO DATA;
SELECT add_continuous_aggregate_policy('orderbook_hourly',
    start_offset => INTERVAL '6 days', end_offset => INTERVAL '1 minute',
    schedule_interval => INTERVAL '5 minutes', if_not_exists => TRUE);
SELECT add_retention_policy('orderbook_hourly', INTERVAL '60 days', if_not_exists => TRUE);
CREATE INDEX IF NOT EXISTS idx_orderbook_hourly_symbol_time ON orderbook_hourly (symbol, time DESC);

CREATE MATERIALIZED VIEW IF NOT EXISTS oi_daily
WITH (timescaledb.continuous) AS
SELECT time_bucket(INTERVAL '1 day', time) AS time,
    exchange, symbol, first(open_interest,time) AS open, max(open_interest) AS high, min(open_interest) AS low, last(open_interest,time) AS close
FROM open_interest 
GROUP BY time_bucket(INTERVAL '1 day', time), exchange, symbol
WITH NO DATA;
SELECT add_continuous_aggregate_policy('oi_daily',
    start_offset => INTERVAL '6 days', end_offset => INTERVAL '1 minute',
    schedule_interval => INTERVAL '5 minutes', if_not_exists => TRUE);
SELECT add_retention_policy('oi_daily', INTERVAL '60 days', if_not_exists => TRUE);
CREATE INDEX IF NOT EXISTS idx_oi_daily_symbol_time ON oi_daily (symbol, time DESC);

CREATE MATERIALIZED VIEW IF NOT EXISTS funding_daily
WITH (timescaledb.continuous) AS
SELECT time_bucket(INTERVAL '1 day', time) AS time,
    exchange, symbol, avg(funding_rate) AS average, min(funding_rate) AS low, max(funding_rate) AS high
FROM funding_rates 
GROUP BY time_bucket(INTERVAL '1 day', time), exchange, symbol
WITH NO DATA;
SELECT add_continuous_aggregate_policy('funding_daily',
    start_offset => INTERVAL '6 days', end_offset => INTERVAL '1 minute',
    schedule_interval => INTERVAL '5 minutes', if_not_exists => TRUE);
SELECT add_retention_policy('funding_daily', INTERVAL '60 days', if_not_exists => TRUE);
CREATE INDEX IF NOT EXISTS idx_funding_daily_symbol_time ON funding_daily (symbol, time DESC);

CREATE MATERIALIZED VIEW IF NOT EXISTS liquidations_daily
WITH (timescaledb.continuous) AS
SELECT time_bucket(INTERVAL '1 day', time) AS time,
    exchange, symbol, count(*) AS count, sum(quantity) AS quantity, sum(CASE WHEN side='buy' THEN quantity ELSE 0 END) AS buy_quantity, sum(CASE WHEN side='sell' THEN quantity ELSE 0 END) AS sell_quantity
FROM liquidations 
GROUP BY time_bucket(INTERVAL '1 day', time), exchange, symbol
WITH NO DATA;
SELECT add_continuous_aggregate_policy('liquidations_daily',
    start_offset => INTERVAL '6 days', end_offset => INTERVAL '1 minute',
    schedule_interval => INTERVAL '5 minutes', if_not_exists => TRUE);
SELECT add_retention_policy('liquidations_daily', INTERVAL '60 days', if_not_exists => TRUE);
CREATE INDEX IF NOT EXISTS idx_liquidations_daily_symbol_time ON liquidations_daily (symbol, time DESC);
