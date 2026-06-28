-- Copyright 2026 Rik Essenius
-- Licensed under the Apache License, Version 2.0. See the LICENSE file for details.
-- File: db/setup.sql

-- run with psql -f db/setup.sql "host=localhost user=postgres dbname=postgres sslmode=require"

-- Create database if not exists (Postgres doesn't have CREATE DATABASE IF NOT EXISTS)

CREATE EXTENSION IF NOT EXISTS dblink;

DO $$
BEGIN
   IF NOT EXISTS (
      SELECT FROM pg_database WHERE datname = 'test'
   ) THEN
      PERFORM dblink_exec('dbname=postgres', 'CREATE DATABASE test');
   END IF;
END$$;

\connect test;

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

-- 'create type if not exists' does not exist
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'series_type') THEN
        CREATE TYPE series_type AS ENUM ('candle', 'value');
    END IF;
END$$;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'series_resolution') THEN
        CREATE TYPE series_resolution AS ENUM ('daily', 'intraday');
    END IF;
END$$;


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
    value       DOUBLE PRECISION NOT NULL,
    PRIMARY KEY (series_id, time)
);

SELECT create_hypertable('prices_intraday', 'time', if_not_exists => TRUE);

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
    series_id   INT NOT NULL REFERENCES series(id),
    time        DATE NOT NULL,
    open        DOUBLE PRECISION,
    high        DOUBLE PRECISION,
    low         DOUBLE PRECISION,
    close       DOUBLE PRECISION,
    volume      DOUBLE PRECISION,
    PRIMARY KEY (series_id, time)
);

SELECT create_hypertable('prices_daily', 'time', if_not_exists => TRUE);

ALTER TABLE prices_daily SET (
    timescaledb.compress,
    timescaledb.compress_segmentby = 'series_id',
    timescaledb.compress_orderby = 'time DESC'
);

SELECT add_compression_policy('prices_daily', INTERVAL '7 days', if_not_exists => TRUE);

-- Reload config to apply telemetry change
SELECT pg_reload_conf();
