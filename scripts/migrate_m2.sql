-- Apply after init_db.sql; pgvector must be installed on the server.
BEGIN;
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS market_features_1m (
    time TIMESTAMPTZ NOT NULL,
    symbol TEXT NOT NULL,
    price_open DOUBLE PRECISION,
    price_high DOUBLE PRECISION,
    price_low DOUBLE PRECISION,
    price_close DOUBLE PRECISION,
    volume DOUBLE PRECISION,
    volume_usd DOUBLE PRECISION,
    price_change_pct DOUBLE PRECISION,
    volatility DOUBLE PRECISION,
    amplitude_pct DOUBLE PRECISION,
    buy_volume_usd DOUBLE PRECISION,
    sell_volume_usd DOUBLE PRECISION,
    delta_usd DOUBLE PRECISION,
    cvd DOUBLE PRECISION,
    trade_count INTEGER,
    buy_sell_ratio DOUBLE PRECISION,
    avg_trade_size_usd DOUBLE PRECISION,
    oi DOUBLE PRECISION,
    oi_usd DOUBLE PRECISION,
    oi_delta DOUBLE PRECISION,
    oi_change_pct DOUBLE PRECISION,
    oi_volume_ratio DOUBLE PRECISION,
    oi_direction TEXT,
    funding_rate DOUBLE PRECISION,
    funding_trend DOUBLE PRECISION,
    bid_depth_10 DOUBLE PRECISION,
    ask_depth_10 DOUBLE PRECISION,
    obi DOUBLE PRECISION,
    spread_bps DOUBLE PRECISION,
    long_liq_usd DOUBLE PRECISION,
    short_liq_usd DOUBLE PRECISION,
    liq_count INTEGER,
    liq_imbalance DOUBLE PRECISION,
    liquidation_intensity DOUBLE PRECISION,
    liquidation_long_short_ratio DOUBLE PRECISION,
    coverage DOUBLE PRECISION NOT NULL CHECK (coverage BETWEEN 0 AND 1),
    quality DOUBLE PRECISION NOT NULL CHECK (quality BETWEEN 0 AND 1),
    age_seconds INTEGER NOT NULL,
    source_flags INTEGER NOT NULL,
    is_final BOOLEAN DEFAULT FALSE,
    revision_count INTEGER,
    PRIMARY KEY (time, symbol)
);
SELECT create_hypertable('market_features_1m', 'time', if_not_exists => TRUE);
CREATE INDEX IF NOT EXISTS idx_features_symbol_time ON market_features_1m(symbol, time DESC);
SELECT add_retention_policy('market_features_1m', INTERVAL '60 days', if_not_exists => TRUE);

CREATE MATERIALIZED VIEW IF NOT EXISTS market_features_5m
WITH (timescaledb.continuous) AS
SELECT time_bucket(INTERVAL '5 minutes', time) AS time, symbol,
    first(price_open,time) AS price_open, max(price_high) AS price_high,
    min(price_low) AS price_low, last(price_close,time) AS price_close,
    sum(volume) AS volume, sum(volume_usd) AS volume_usd,
    sum(delta_usd) AS delta_usd, last(cvd,time) AS cvd,
    last(oi,time) AS oi, last(funding_rate,time) AS funding_rate,
    avg(obi) AS obi, sum(long_liq_usd) AS long_liq_usd,
    sum(short_liq_usd) AS short_liq_usd, min(quality) AS quality
FROM market_features_1m
GROUP BY time_bucket(INTERVAL '5 minutes', time), symbol WITH NO DATA;
SELECT add_continuous_aggregate_policy('market_features_5m',
    start_offset => INTERVAL '59 days', end_offset => INTERVAL '5 minutes',
    schedule_interval => INTERVAL '5 minutes', if_not_exists => TRUE);
CREATE INDEX IF NOT EXISTS idx_features_5m_symbol_time ON market_features_5m(symbol, time DESC);

CREATE MATERIALIZED VIEW IF NOT EXISTS market_features_1h
WITH (timescaledb.continuous) AS
SELECT time_bucket(INTERVAL '1 hour', time) AS time, symbol,
    first(price_open,time) AS price_open, max(price_high) AS price_high,
    min(price_low) AS price_low, last(price_close,time) AS price_close,
    sum(volume) AS volume, sum(volume_usd) AS volume_usd,
    sum(delta_usd) AS delta_usd, last(cvd,time) AS cvd,
    last(oi,time) AS oi, last(funding_rate,time) AS funding_rate,
    avg(obi) AS obi, sum(long_liq_usd) AS long_liq_usd,
    sum(short_liq_usd) AS short_liq_usd, min(quality) AS quality
FROM market_features_1m
GROUP BY time_bucket(INTERVAL '1 hour', time), symbol WITH NO DATA;
SELECT add_continuous_aggregate_policy('market_features_1h',
    start_offset => INTERVAL '59 days', end_offset => INTERVAL '1 hour',
    schedule_interval => INTERVAL '1 hour', if_not_exists => TRUE);
CREATE INDEX IF NOT EXISTS idx_features_1h_symbol_time ON market_features_1h(symbol, time DESC);

CREATE MATERIALIZED VIEW IF NOT EXISTS market_features_1d
WITH (timescaledb.continuous) AS
SELECT time_bucket(INTERVAL '1 day', time) AS time, symbol,
    first(price_open,time) AS price_open, max(price_high) AS price_high,
    min(price_low) AS price_low, last(price_close,time) AS price_close,
    sum(volume) AS volume, sum(volume_usd) AS volume_usd,
    sum(delta_usd) AS delta_usd, last(cvd,time) AS cvd,
    last(oi,time) AS oi, last(funding_rate,time) AS funding_rate,
    avg(obi) AS obi, sum(long_liq_usd) AS long_liq_usd,
    sum(short_liq_usd) AS short_liq_usd, min(quality) AS quality
FROM market_features_1m
GROUP BY time_bucket(INTERVAL '1 day', time), symbol WITH NO DATA;
SELECT add_continuous_aggregate_policy('market_features_1d',
    start_offset => INTERVAL '59 days', end_offset => INTERVAL '1 day',
    schedule_interval => INTERVAL '1 day', if_not_exists => TRUE);
CREATE INDEX IF NOT EXISTS idx_features_1d_symbol_time ON market_features_1d(symbol, time DESC);

CREATE TABLE IF NOT EXISTS feature_analysis_tasks (
    id UUID PRIMARY KEY,
    symbol TEXT NOT NULL,
    start_time TIMESTAMPTZ NOT NULL,
    end_time TIMESTAMPTZ NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('pending','running','completed','failed')),
    result JSONB, error TEXT,
    owner_id UUID, lease_expires_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS feature_containers (
    id UUID PRIMARY KEY,
    name TEXT UNIQUE NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS feature_cases (
    id UUID PRIMARY KEY,
    task_id UUID NOT NULL REFERENCES feature_analysis_tasks(id),
    container_id UUID REFERENCES feature_containers(id) ON DELETE SET NULL,
    symbol TEXT NOT NULL,
    title TEXT NOT NULL,
    analysis JSONB NOT NULL,
    feature_snapshot JSONB NOT NULL,
    outcome TEXT CHECK (outcome IN ('success','failure')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_cases_container ON feature_cases(container_id);
CREATE TABLE IF NOT EXISTS feature_vectors (
    case_id UUID PRIMARY KEY REFERENCES feature_cases(id) ON DELETE CASCADE,
    embedding vector(1536) NOT NULL,
    model TEXT NOT NULL,
    representation TEXT NOT NULL DEFAULT 'market-window-v1'
);
CREATE INDEX IF NOT EXISTS idx_case_vectors_cosine ON feature_vectors
    USING hnsw (embedding vector_cosine_ops);
CREATE TABLE IF NOT EXISTS opportunities (
    symbol TEXT PRIMARY KEY,
    observed_at TIMESTAMPTZ NOT NULL,
    expires_at TIMESTAMPTZ NOT NULL,
    stage TEXT NOT NULL,
    similarity DOUBLE PRECISION NOT NULL,
    confidence DOUBLE PRECISION NOT NULL,
    historical_success_rate DOUBLE PRECISION,
    labeled_cases INTEGER NOT NULL,
    matches JSONB NOT NULL
);
COMMIT;
