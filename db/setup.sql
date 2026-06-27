-- Copyright 2026 Rik Essenius
-- Licensed under the Apache License, Version 2.0. See the LICENSE file for details.
-- File: db/setup.sql

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

CREATE TABLE IF NOT EXISTS asset (
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

CREATE INDEX IF NOT EXISTS asset_symbol_idx ON asset (symbol);
CREATE INDEX IF NOT EXISTS asset_name_idx ON asset (name);
CREATE INDEX IF NOT EXISTS asset_provider_idx ON asset (provider);

-- ============================
-- Series table
-- ============================

CREATE TYPE IF NOT EXISTS series_type AS ENUM ('candle', 'value');
CREATE TYPE IF NOT EXISTS series_resolution AS ENUM ('daily', 'intraday');

CREATE TABLE IF NOT EXISTS series (
    id SERIAL PRIMARY KEY,
    asset_id INTEGER NOT NULL REFERENCES asset(id),
    resolution series_resolution NOT NULL,
    series_type series_type NOT NULL,
    interval TEXT NOT NULL,
    history_limit TEXT NOT NULL,

    UNIQUE(asset_id, resolution)
);

CREATE INDEX IF NOT EXISTS series_asset_id_idx ON series (asset_id);
CREATE INDEX IF NOT EXISTS series_resolution_type_idx ON series (resolution, series_type);
CREATE INDEX IF NOT EXISTS series_type_idx ON series (series_type);
-- ============================
-- Intraday hypertable
-- ============================

CREATE TABLE IF NOT EXISTS prices_intraday (
    series_id   INT NOT NULL REFERENCES series(id),
    time        TIMESTAMPTZ NOT NULL,
    value       DOUBLE PRECISION NOT NULL
);

SELECT create_hypertable('prices_intraday', 'time', if_not_exists => TRUE);

ALTER TABLE prices_intraday ADD PRIMARY KEY (series_id, time);

CREATE INDEX IF NOT EXISTS prices_intraday_series_time_idx ON prices_intraday (series_id, time DESC);

ALTER TABLE prices_intraday SET (
    timescaledb.compress,
    timescaledb.compress_segmentby = 'series_id',
    timescaledb.compress_orderby = 'time DESC'
);

SELECT add_compression_policy('prices_intraday', INTERVAL '3 days', if_not_exists => TRUE);

-- Retention: 30 days
SELECT add_retention_policy('prices_intraday', INTERVAL '30 days', if_not_exists => TRUE);

-- Compression: after 3 days

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

ALTER TABLE prices_daily ADD PRIMARY KEY (series_id, time);

CREATE INDEX IF NOT EXISTS prices_daily_series_time_idx ON prices_daily (series_id, time DESC);

ALTER TABLE prices_daily SET (
    timescaledb.compress,
    timescaledb.compress_segmentby = 'series_id',
    timescaledb.compress_orderby = 'time DESC'
);

SELECT add_compression_policy('prices_daily', INTERVAL '7 days', if_not_exists => TRUE);

-- Reload config to apply telemetry change
SELECT pg_reload_conf();
