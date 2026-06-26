-- run with psql -f db/setup.sql "host=... sslmode=require ..."

-- Create database if not exists (Postgres doesn't have CREATE DATABASE IF NOT EXISTS)
DO $$
BEGIN
   IF NOT EXISTS (
      SELECT FROM pg_database WHERE datname = 'finance'
   ) THEN
      PERFORM dblink_exec('dbname=postgres', 'CREATE DATABASE finance');
   END IF;
END$$;

\connect finance;

-- Enable TimescaleDB
CREATE EXTENSION IF NOT EXISTS timescaledb;

-- Disable telemetry
ALTER SYSTEM SET timescaledb.telemetry_level = 'off';

-- ============================
-- Asset table
-- ============================

CREATE TABLE asset (
    id            SERIAL PRIMARY KEY,
    -- identity/logic
    name          TEXT NOT NULL,
    symbol        TEXT NOT NULL,
    provider      TEXT NOT NULL,
    provider_code TEXT NOT NULL,

    -- metadata
    display_name  TEXT,
    instrument    TEXT,
    region        TEXT,
    exchange      TEXT,
    currency      TEXT,
    unit          TEXT,
    UNIQUE(name),
    -- we can have different providers for daily and intraday
    UNIQUE(provider, symbol),
    UNIQUE(provider, provider_code)
);

-- ============================
-- Series table
-- ============================

CREATE TYPE series_type AS ENUM ('candle', 'value');
CREATE TYPE series_resolution AS ENUM ('daily', 'intraday');

CREATE TABLE series (
    id SERIAL PRIMARY KEY,
    asset_id INTEGER NOT NULL REFERENCES asset(id),
    resolution series_resolution NOT NULL,
    series_type series_type NOT NULL,
    interval TEXT NOT NULL,
    history_limit TEXT NOT NULL

    UNIQUE (asset_id, resolution)
);

-- ============================
-- Intraday hypertable
-- ============================

CREATE TABLE IF NOT EXISTS prices_intraday (
    time        TIMESTAMPTZ NOT NULL,
    series_id   INT NOT NULL REFERENCES series(id),
    value       DOUBLE PRECISION NOT NULL
);

SELECT create_hypertable('prices_intraday', 'time', if_not_exists => TRUE);

-- Retention: 30 days
SELECT add_retention_policy('prices_intraday', INTERVAL '30 days', if_not_exists => TRUE);

-- Compression: after 3 days
ALTER TABLE intraday_prices SET (timescaledb.compress);
SELECT add_compression_policy('prices_intraday', INTERVAL '3 days', if_not_exists => TRUE);

-- ============================
-- Daily hypertable
-- ============================

CREATE TABLE IF NOT EXISTS prices_daily (
    time        DATE NOT NULL,
    series_id   INT NOT NULL REFERENCES series(id),
    open        DOUBLE PRECISION,
    high        DOUBLE PRECISION,
    low         DOUBLE PRECISION,
    close       DOUBLE PRECISION,
    volume      DOUBLE PRECISION
);

SELECT create_hypertable('prices_daily', 'time', if_not_exists => TRUE);

-- Daily data kept forever (no retention)
-- Compression: after 7 days
ALTER TABLE prices_daily SET (timescaledb.compress, timescaledb.compress_segmentby = 'series_id');
SELECT add_compression_policy('prices_daily', INTERVAL '7 days', if_not_exists => TRUE);

-- Reload config to apply telemetry change
SELECT pg_reload_conf();
