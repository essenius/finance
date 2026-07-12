-- Copyright 2026 Rik Essenius
-- Licensed under the Apache License, Version 2.0. See the LICENSE file for details.
-- File: db/setup.sql

-- run with psql -h localhost -U postgres -f db/setup.sql
-- set credentials in ~/.pgpass: localhost:5432:*:postgres:password:sslmode=verify-all

-- Create database if not exists (Postgres doesn't have CREATE DATABASE IF NOT EXISTS)

\set dbname test

CREATE EXTENSION IF NOT EXISTS dblink;

SELECT EXISTS (
    SELECT FROM pg_database WHERE datname = :'dbname'
) AS db_exists
\gset

\if :db_exists
    \echo Database :dbname already exists
\else
    \echo Creating database :dbname
    SELECT dblink_exec(
        'dbname=postgres',
        'CREATE DATABASE ' || quote_ident(:'dbname')
    );
\endif

\connect :dbname

-- Enable TimescaleDB
CREATE EXTENSION IF NOT EXISTS timescaledb;

-- Disable telemetry
ALTER SYSTEM SET timescaledb.telemetry_level = 'off';

CREATE SCHEMA bootstrap;

CREATE OR REPLACE FUNCTION bootstrap.job_exists(
    tablename name,
    procname text
)
RETURNS boolean LANGUAGE sql AS $$
    SELECT EXISTS (
        SELECT 1
        FROM timescaledb_information.jobs
        WHERE hypertable_name = tablename::text
          AND proc_name = procname
    );
$$;

CREATE OR REPLACE FUNCTION bootstrap.table_exists(tablename name)
RETURNS boolean LANGUAGE sql AS $$
    SELECT EXISTS (
        SELECT 1
        FROM pg_class
        WHERE relname = tablename::text
          AND relkind = 'r'
    );
$$;

CREATE OR REPLACE FUNCTION bootstrap.hypertable_exists(tablename name)
RETURNS boolean LANGUAGE sql AS $$
    SELECT EXISTS (
        SELECT 1
        FROM timescaledb_information.hypertables
        WHERE hypertable_name = tablename::text
    );
$$;

CREATE OR REPLACE FUNCTION bootstrap.create_series_indexes(tbl_name text)
RETURNS void LANGUAGE plpgsql AS $$
BEGIN
    -- Index on series_id
    EXECUTE format(
        'CREATE INDEX IF NOT EXISTS %I_series_id_idx ON %I (series_id);',
        tbl_name, tbl_name
    );
END;
$$;


CREATE OR REPLACE FUNCTION bootstrap.create_data_table(
    tablename name,
    compress_after interval,
    retention_after interval,
    chunk_interval interval
)
RETURNS void LANGUAGE plpgsql AS $$
DECLARE
    is_ht bool;
BEGIN
    -- Create the table
    IF NOT EXISTS (
        SELECT 1
        FROM pg_class
        WHERE relname = tablename::text
        AND relkind = 'r'
    ) THEN
        EXECUTE format($sql$
            CREATE TABLE %I (
                series_id   INT NOT NULL REFERENCES series(id),
                time        TIMESTAMPTZ NOT NULL,
                open        DOUBLE PRECISION,
                high        DOUBLE PRECISION,
                low         DOUBLE PRECISION,
                close       DOUBLE PRECISION NOT NULL,
                volume      DOUBLE PRECISION,
                PRIMARY KEY (series_id, time)
            );
        $sql$, tablename);
    END IF;

    -- Convert to hypertable
    IF NOT bootstrap.hypertable_exists(tablename) THEN
        PERFORM create_hypertable(
            tablename::regclass,
            'time',
            chunk_time_interval => chunk_interval
        );
    END IF;

    -- 3. Apply compression settings

    EXECUTE format(
        'ALTER TABLE %I SET (
            timescaledb.compress,
            timescaledb.compress_segmentby = ''series_id'',
            timescaledb.compress_orderby = ''time DESC''
        )',
        tablename
    );

    -- Add compression policy
    IF NOT bootstrap.job_exists(tablename, 'policy_compression') THEN
        PERFORM add_compression_policy(tablename::regclass, compress_after);
    END IF;

    -- Add retention policy (optional)
    IF retention_after IS NOT NULL
       AND NOT bootstrap.job_exists(tablename, 'policy_retention') THEN
        PERFORM add_retention_policy(tablename::regclass, retention_after);
    END IF;

    PERFORM bootstrap.create_series_indexes(tablename);

END;
$$;

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

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'completion_policy') THEN
        CREATE TYPE completion_policy AS ENUM ('interval_close', 'next_day');
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
    completion_policy completion_policy NOT NULL,

    UNIQUE(asset_id, code)
);

CREATE INDEX IF NOT EXISTS series_asset_id_idx ON series (asset_id);
CREATE INDEX IF NOT EXISTS series_retention_idx ON series (retention);

-- ============================
-- Hypertables
-- ============================

SELECT bootstrap.create_data_table('series_data_cold'::name, '7 days'::interval, NULL::interval, '1 month'::interval);
SELECT bootstrap.create_data_table('series_data_hot'::name, '3 days'::interval, '30 days'::interval, '1 day'::interval);

-- Reload config to apply telemetry change
SELECT pg_reload_conf();


CREATE OR REPLACE VIEW series_with_asset AS
SELECT
    s.id AS series_id,
    s.code as series_code,
    s.asset_id,
    a.name AS asset_name,
    a.name || ':' || s.code AS series_name,
    a.provider,
    a.provider_code,
    a.symbol,
    a.display_name,
    a.instrument,
    a.region,
    a.exchange,
    a.currency,
    a.unit,
    s.interval,
    s.retention,
    s.series_type,
    s.bootstrap_history,
    s.completion_policy
FROM series s JOIN asset a ON s.asset_id = a.id ORDER BY series_id ASC;
