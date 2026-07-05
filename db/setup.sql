-- Copyright 2026 Rik Essenius
-- Licensed under the Apache License, Version 2.0. See the LICENSE file for details.
-- File: db/setup.sql

-- run with psql -f db/setup.sql "host=localhost user=postgres dbname=postgres sslmode=require"

-- Create database if not exists (Postgres doesn't have CREATE DATABASE IF NOT EXISTS)

\set dbname finance

CREATE EXTENSION IF NOT EXISTS dblink;

DO $$
DECLARE
    dbname text := ':dbname';
BEGIN
   RAISE NOTICE 'Database name is: %', dbname;
   IF NOT EXISTS (
      SELECT FROM pg_database WHERE datname = dbname
   ) THEN
        EXECUTE format(
            'SELECT dblink_exec(%L, %L)',
            'dbname=postgres',
            'CREATE DATABASE ' || quote_ident(dbname)
        );
    END IF;
END$$;

\connect :dbname

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
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'series_retention') THEN
        CREATE TYPE series_retention AS ENUM ('short_lived', 'long_lived');
    END IF;
END$$;


CREATE TABLE IF NOT EXISTS series (
    id SERIAL PRIMARY KEY,
    code TEXT NOT NULL,
    asset_id INTEGER NOT NULL REFERENCES asset(id),
    interval TEXT NOT NULL,
    series_type series_type NOT NULL,
    retention series_retention NOT NULL,
    bootstrap_history TEXT NOT NULL,

    UNIQUE(asset_id, code)
);

CREATE INDEX IF NOT EXISTS series_asset_id_idx ON series (asset_id);
CREATE INDEX IF NOT EXISTS series_retention_idx ON series (retention);

-- ============================
-- Hypertables
-- ============================

-- Cold (long-lived)

CREATE TABLE IF NOT EXISTS series_data_cold (
    series_id   INT NOT NULL REFERENCES series(id),
    time        TIMESTAMPTZ NOT NULL,
    open        DOUBLE PRECISION,
    high        DOUBLE PRECISION,
    low         DOUBLE PRECISION,
    close       DOUBLE PRECISION,
    volume      DOUBLE PRECISION,
    PRIMARY KEY (series_id, time)
);

SELECT create_hypertable('series_data_cold', 'time', if_not_exists => TRUE);

ALTER TABLE series_data_cold SET (
    timescaledb.compress,
    timescaledb.compress_segmentby = 'series_id',
    timescaledb.compress_orderby = 'time DESC'
);

SELECT add_compression_policy('series_data_cold', INTERVAL '7 days', if_not_exists => TRUE);

-- Hot (short-lived)

CREATE TABLE IF NOT EXISTS series_data_hot (LIKE series_data_cold INCLUDING ALL);

SELECT create_hypertable('series_data_hot', 'time', if_not_exists => TRUE);

ALTER TABLE series_data_hot SET (
    timescaledb.compress,
    timescaledb.compress_segmentby = 'series_id',
    timescaledb.compress_orderby = 'time DESC'
);

SELECT add_compression_policy('series_data_hot', INTERVAL '3 days', if_not_exists => TRUE);

SELECT add_retention_policy('series_data_hot', INTERVAL '30 days', if_not_exists => TRUE);


-- Reload config to apply telemetry change
SELECT pg_reload_conf();
