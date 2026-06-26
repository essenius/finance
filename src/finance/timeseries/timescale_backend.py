# Copyright 2026 Rik Essenius
# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.
# File: src/finance/timeseries/timescale_backend.py

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime

# import side-effectful functions like 'connect' via module (so you can easily mock)
import psycopg

# import helpers directly
from psycopg import sql

from finance.common.applogger import AppLogger
from finance.common.model import (
    Asset,
    CandlePoint,
    DailyValuePoint,
    IntradayPoint,
    Result,
    Series,
    SeriesPoint,
)

logger = AppLogger()


@dataclass
class TimescaleConfig:
    host: str
    dbname: str
    user: str
    password: str
    port: int = 5432
    sslmode: str = "verify-ca"

    max_batch_size: int = 1000
    max_batch_age_seconds: float = 2.0


class TimescaleBackend:
    def __init__(self, config: TimescaleConfig, now: Callable[[], datetime] = None) -> None:
        self._config: TimescaleConfig = config
        self._connection = None
        self._pending: list[SeriesPoint] = []
        self._last_flush: datetime | None = None
        self.now = now or (lambda: datetime.now(UTC))
        self._intraday_series_ids: set[int] = set()

    @classmethod
    def from_config(cls, config: dict, now: Callable[[], datetime] = None) -> Result[TimescaleBackend]:
        try:
            ts_config = TimescaleConfig(
                host=config["host"],
                port=config.get("port", 5432),
                dbname=config["db"],
                user=config["user"],
                password=config["password"],
                sslmode=config.get("ssl_mode", "verify-ca"),
                max_batch_size=config.get("max_batch_size", 1000),
                max_batch_age_seconds=config.get("max_batch_age_seconds", 2.0),
            )

            # Pure: no I/O
            backend = cls(ts_config, now)
            backend.refresh_intraday_series_ids()
            return Result.ok_payload(backend)

        except KeyError as ke:
            return Result.fail("Timescale backend initialization failed", f"Cannot find mandatory config key {ke}")

    # ------------------------------------------------------------
    # Utilities
    # ------------------------------------------------------------

    def ensure_connected(self) -> Result[None]:
        if self.is_connected():
            return Result.ok_payload(None)

        try:
            self._connection = psycopg.connect(**self._config.__dict__)
        except Exception as exc:
            return Result.fail("Connect failed", exc)

        return Result.ok_payload(None)

    def is_connected(self) -> bool:
        conn = self._connection
        return conn is not None and not conn.closed

    def _database_operation(self, fn, context: str = "Database") -> Result:
        """
        wrap database operations with a connection and error check
        """
        ensure = self.ensure_connected()
        if not ensure.ok:
            return ensure

        try:
            return fn()
        except Exception as exc:
            return Result.fail(f"{context} operation failed", exc)

    def _execute_read(self, sql: str, params: tuple | None = None):
        """
        Execute a SELECT query and return all rows. Run this in a _database_operation.
        """
        cur = self._connection.cursor()
        cur.execute(sql, params or ())
        rows = cur.fetchall()
        cur.close()
        return rows

    # ------------------------------------------------------------
    # Handling of series points
    # ------------------------------------------------------------

    def add(self, entry: SeriesPoint) -> Result[None]:
        """Buffer a new price entry and flush based on batch size or age."""
        self._pending.append(entry)

        if self._should_flush():
            return self.flush()

        return Result.ok_payload(None)

    def _should_flush(self) -> bool:
        now = self.now()
        if self._last_flush is None:
            self._last_flush = now

        if not self._pending:
            return False
        # Flush by size
        if len(self._pending) >= self._config.max_batch_size:
            return True
        age = (now - self._last_flush).total_seconds()
        if age >= self._config.max_batch_age_seconds:
            return True
        return False

    def flush(self) -> Result[None]:
        """Flush all pending entries to TimescaleDB."""

        if not self._pending:
            return Result.ok_payload(None)

        # Perform all batch inserts inside a single safe transaction
        result = self._insert_batches(self._pending, "Flush")
        if not result.ok:
            return result

        self._pending.clear()
        self._last_flush = self.now()
        return Result.ok_payload(None)

    def close(self) -> Result[None]:
        """Flush pending data and close the DB connection."""
        result = self.flush()
        self._connection.close()
        return result

    # ------------------------------------------------------------
    # batch write helpers
    # ------------------------------------------------------------

    def _insert_batches(self, entries: list[SeriesPoint], context: str) -> Result[None]:
        """
        Data-driven batch insertion for all SeriesPoint subclasses.
        """

        sql_template = """
            INSERT INTO {table} (
                series_id, ts{extra_fields}
            ) VALUES (%s, %s{placeholders})
        """

        # Define the batch types
        batch_specs = [
            (
                CandlePoint,
                "prices_daily",
                ["open", "high", "low", "close", "volume"],
                lambda e: (e.open, e.high, e.low, e.close, e.volume),
            ),
            (DailyValuePoint, "prices_daily", ["close"], lambda e: (e.value,)),
            (IntradayPoint, "prices_intraday", ["value"], lambda e: (e.value,)),
        ]

        # Group entries by type
        grouped: dict[type, list] = {spec[0]: [] for spec in batch_specs}

        for p in entries:
            for cls, _, _, _ in batch_specs:
                if isinstance(p, cls):
                    grouped[cls].append(p)
                    break
            else:
                return Result.fail("Flush failed", f"Unsupported SeriesPoint subtype: {type(p).__name__}")

        # Execute batches
        for cls, table, fields, extractor in batch_specs:
            batch = grouped[cls]
            if not batch:
                continue

            extra_fields = "".join(f", {f}" for f in fields)
            placeholders = "".join(", %s" for _ in fields)

            sql_stmt = sql.SQL(sql_template.format(table=table, extra_fields=extra_fields, placeholders=placeholders))
            values = [(e.series_id, e.timestamp, *extractor(e)) for e in batch]

            result = self._execute_many(sql_stmt, values, context)
            if not result.ok:
                return result

        return Result.ok_payload(None)

    def _execute_many(self, sql: str, params: list[tuple], context: str) -> Result[None]:

        def operation():
            with self._connection:
                with self._connection.cursor() as cur:
                    cur.executemany(sql, params)
            return Result.ok_payload(None)

        return self._database_operation(operation, context)

    # ------------------------------------------------------------
    # Reading first and last
    # ------------------------------------------------------------

    def read_first(self, series_id: int) -> Result[SeriesPoint]:
        """
        Return the earliest point for this series_id as a typed SeriesPoint.
        """
        return self._read_one(series_id, ascending=True, context="Read first")

    def read_last(self, series_id: int) -> Result[SeriesPoint]:
        """
        Return the latest point for this series_id as a typed SeriesPoint.
        """
        return self._read_one(series_id, ascending=False, context="Read last")

    def _read_one(self, series_id: int, *, ascending: bool, context: str) -> Result[SeriesPoint | None]:
        """
        Read a single row (first or last) from the correct Timescale table.
        """

        def operation():
            if series_id is None:
                return Result.fail(f"Series id not set for {context}")

            is_intraday = series_id in self._intraday_series_ids
            table = "prices_intraday" if is_intraday else "prices_daily"
            order = sql.SQL("ASC") if ascending else sql.SQL("DESC")

            stmt = sql.SQL("""
                SELECT series_id, ts, open, high, low, close, volume, price FROM {table}
                WHERE series_id = %s ORDER BY ts {order} LIMIT 1
            """).format(
                table=sql.Identifier(table),
                order=order,
            )

            with self._connection.cursor() as cur:
                cur.execute(stmt, (series_id,))
                row = cur.fetchone()
                if not row:
                    return Result.ok_payload(None)

                # following row layout

                if is_intraday:
                    sid, timestamp, value = row
                    return Result.ok_payload(IntradayPoint(series_id=sid, timestamp=timestamp, value=value))

                sid, timestamp, open, high, low, close, volume = row

                # Daily table: candle or daily-value. Guess the real type based on content
                # open can be None if we used synthetic data from metadata
                if volume is not None or high is not None or low is not None:
                    return Result.ok_payload(
                        CandlePoint(
                            series_id=sid,
                            timestamp=timestamp,
                            open=open,
                            high=high,
                            low=low,
                            close=close,
                            volume=volume,
                        )
                    )

                # Daily value (close-only)
                return Result.ok_payload(DailyValuePoint(series_id=sid, timestamp=timestamp, value=close))

        return self._database_operation(operation, context)

    # ------------------------------------------------------------
    # Persisting assets and series
    # ------------------------------------------------------------

    def refresh_intraday_series_ids(self) -> None:
        """
        Load all intraday series IDs into a set for fast lookup during state rebuild.
        """
        sql = "SELECT id FROM series WHERE resolution = 'intraday';"

        def operation():
            rows = self._execute_read(sql)
            self._intraday_series_ids = {row.id for row in rows}

        return self._database_operation(operation, "load intraday series ids")

    def store_asset(self, a: Asset) -> Result[Asset]:
        """
        Insert or update an asset row.
        YAML is authoritative, so we upsert on (symbol, provider).
        """

        metadata = (
            a.symbol,
            a.provider,
            a.provider_code,
            a.display_name,
            a.instrument,
            a.region,
            a.exchange,
            a.currency,
            a.unit,
        )
        if a.id is None:
            sql = """
                    INSERT INTO asset (name, symbol, provider, provider_code, display_name, instrument, region, exchange, currency, unit)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    RETURNING id;
                    """

            params = (a.name, *metadata)

        else:
            # UPDATE
            sql = """
                UPDATE asset
                SET symbol=%s, provider=%s, provider_code=%s, display_name=%s, instrument=%s, region=%s, exchange=%s, currency=%s, unit=%s
                WHERE id=%s
                RETURNING id;
            """

            params = (*metadata, a.id)

        result = self._execute_write(sql, params)

        if not result.ok:
            return result
        return Result.ok_payload(a if a.id is not None else a.with_id(result.payload))

    def store_series(self, series: Series) -> Result[Series]:
        """
        Insert or update a series row.
        YAML is authoritative, so we upsert on (asset_id, resolution).
        """

        metadata = (series.series_type, series.interval, series.history_limit)

        if series.id is None:
            # INSERT
            sql = """
                INSERT INTO series (asset_id, resolution, series_type, interval, history_limit)
                VALUES (%s, %s, %s, %s, %s)
                RETURNING id;
            """
            params = (series.asset_id, series.resolution, *metadata)

        else:
            # UPDATE
            sql = """
                UPDATE series SET series_type=%s, interval=%s, history_limit=%s WHERE id=%s RETURNING id;
            """

            params = (*metadata, series.id)

        result = self._execute_write(sql, params)
        if not result.ok:
            return result

        return Result.ok_payload(series if series.id is not None else series.with_id(result.payload))

    def _execute_write(self, sql: str, params: tuple) -> Result[int]:

        def operation():
            with self._connection, self._connection.cursor() as cursor:
                cursor.execute(sql, params)
                new_id = cursor.fetchone()[0]
                return Result.ok_payload(new_id)

        return self._database_operation(operation, "write")

    # ------------------------------------------------------------
    # Retrieving assets and series
    # ------------------------------------------------------------

    def get_assets(self) -> Result[list[Asset]]:
        """
        Retrieve all assets from the database as Asset model objects.
        """

        def operation():
            with self._connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT id, name, symbol, provider, provider_code, display_name, instrument, region, exchange, currency, unit FROM asset ORDER BY id;
                    """
                )
                rows = cursor.fetchall()
            return Result.ok_payload(
                [
                    Asset(
                        id=row[0],
                        name=row[1],
                        symbol=row[2],
                        provider=row[3],
                        provider_code=row[4],
                        display_name=row[5],
                        instrument=row[6],
                        region=row[7],
                        exchange=row[8],
                        currency=row[9],
                        unit=row[10],
                    )
                    for row in rows
                ]
            )

        return self._database_operation(operation, "get_assets")

    def get_series(self) -> Result[list[Series]]:
        """
        Retrieve all series rows from the database and return them as Series model objects.
        """

        def operation():

            with self._connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT s.id, s.asset_id, a.name as symbol,  a.symbol || '_' || s.resolution AS name,
                           s.resolution, s.series_type, s.interval, s.history_limit FROM series s
                    JOIN asset a ON s.asset_id = a.id
                    ORDER BY s.id;
                    """
                )
                rows = cursor.fetchall()

            return Result.ok_payload(
                [
                    Series(
                        id=row[0],
                        asset_id=row[1],
                        symbol=row[2],
                        name=row[3],
                        resolution=row[4],
                        series_type=row[5],
                        interval=row[6],
                        history_limit=row[7],
                    )
                    for row in rows
                ]
            )

        return self._database_operation(operation, "get_series")
