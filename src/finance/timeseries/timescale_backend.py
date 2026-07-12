# Copyright 2026 Rik Essenius
# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.
# File: src/finance/timeseries/timescale_backend.py

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

# import side-effectful functions like 'connect' via module (so you can easily mock)
import psycopg

# import helpers directly
from psycopg import sql

from finance.common.applogger import AppLogger
from finance.common.model import (
    BACKEND,
    Asset,
    Result,
    Retention,
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
    sslmode: str = "verify-full"
    sslrootcert: str = "system"

    max_batch_size: int = 1000
    max_batch_age: timedelta = timedelta(seconds=2.0)

    CONNECTION_FIELDS = ("host", "port", "dbname", "user", "password", "sslmode", "sslrootcert")

    def connect_config(self) -> dict:
        return {field: getattr(self, field) for field in self.CONNECTION_FIELDS}


class TimescaleBackend:
    def __init__(
        self, config: TimescaleConfig, series_by_id: Callable[[int], Series], now: Callable[[], datetime] = None
    ) -> None:
        self._config: TimescaleConfig = config
        self._series_by_id = series_by_id
        self._connection = None
        self._pending: list[SeriesPoint] = []
        self._last_flush: datetime | None = None
        self.now = now or (lambda: datetime.now(UTC))
        self._short_lived_series_ids: set[int] = set()

    @classmethod
    def from_config(
        cls, config: dict, series_by_id: Callable[[int], Series], now: Callable[[], datetime] = None
    ) -> Result[TimescaleBackend]:
        try:
            ts_config = TimescaleConfig(
                host=config["host"],
                port=config.get("port", 5432),
                dbname=config["db"],
                user=config["user"],
                password=config["password"],
                sslmode=config.get("ssl_mode", "verify-full"),
                sslrootcert=config.get("ssl_root_cert", "system"),
                max_batch_size=config.get("max_batch_size", 1000),
                max_batch_age=timedelta(seconds=config.get("max_batch_age_seconds", 2.0)),
            )

            if ts_config.sslmode == "verify-ca" and ts_config.sslrootcert == "system":
                return Result.fail(
                    "Timescale backend initialization failed",
                    f"verify-ca requires path in {BACKEND.upper()}_SSL_ROOT_CERT in .env or ssl_root_cert in yaml",
                )

            backend = cls(ts_config, series_by_id, now)
            refresh_result = backend.refresh_short_lived_series_ids()
            if not refresh_result.ok:
                return refresh_result
            return Result.ok_payload(backend)

        except KeyError as ke:
            return Result.fail("Timescale backend initialization failed", f"Cannot find mandatory config key {ke}")

    # ------------------------------------------------------------
    # Utilities
    # ------------------------------------------------------------

    def _connect(self):
        print("CONNECT FROM:", psycopg.connect)
        return psycopg.connect(**self._config.connect_config())

    def ensure_connected(self) -> Result[None]:
        if self.is_connected():
            return Result.ok_payload(None)

        try:
            conn = self._connect()
        except Exception as exc:
            return Result.fail("Connect failed", exc)

        # probe query to check permissions
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT id from series LIMIT 1")
        except Exception as exc:
            conn.rollback()  # clear aborted state
            return Result.fail("Database startup failed", exc)
        self._connection = conn
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

    def add(self, entry: SeriesPoint) -> Result[int]:
        """Buffer a new point and flush based on batch size or age. Returns the number of records written to the database, wrapped in a Result.
        These are always the oldest records in the queue"""
        self._pending.append(entry)

        if self._should_flush():
            return self.flush()

        return Result.ok_payload(0)

    def _should_flush(self) -> bool:
        now = self.now()
        if self._last_flush is None:
            self._last_flush = now

        if not self._pending:
            return False
        # Flush by size
        if len(self._pending) >= self._config.max_batch_size:
            return True
        age = now - self._last_flush
        if age >= self._config.max_batch_age:
            return True
        return False

    def flush(self) -> Result[int]:
        """Flush all pending entries to TimescaleDB. Returns the number of entries written, wrapped in a Result"""

        if not self._pending:
            return Result.ok_payload(0)

        # Perform all batch inserts inside a single safe transaction.
        result = self._insert_batches(self._pending, "Flush")
        # clear the pending items regardless if succeeded or not. THe WAL will need to re-insert after failure.
        self._pending.clear()
        if result.ok:
            self._last_flush = self.now()

        # pass on the number of flushed records wrapped in a Result
        return result

    def close(self) -> Result[int]:
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
        Inserts
        """
        sql_template = """
        INSERT INTO {table} (series_id, time, open, high, low, close, volume)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (series_id, time)
        DO UPDATE SET
            open   = EXCLUDED.open,
            high   = EXCLUDED.high,
            low    = EXCLUDED.low,
            close  = EXCLUDED.close,
            volume = EXCLUDED.volume
        """

        points: dict[str, list] = {"hot": [], "cold": []}
        for point in entries:
            label = "hot" if point.series_id in self._short_lived_series_ids else "cold"
            points[label].append(point)

        # Execute batches
        for label, point_list in points.items():
            table = f"series_data_{label}"
            sql_stmt = sql.SQL(sql_template.format(table=table))
            values = [(e.series_id, e.time, e.open, e.high, e.low, e.close, e.volume) for e in point_list]

            result = self._execute_many(sql_stmt, values, context)
            if not result.ok:
                return result

        return Result.ok_payload(len(entries))

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

            label = "hot" if series_id in self._short_lived_series_ids else "cold"
            table = f"series_data_{label}"
            order = sql.SQL("ASC") if ascending else sql.SQL("DESC")

            stmt = sql.SQL("""
                SELECT series_id, time, open, high, low, close, volume FROM {table}
                WHERE series_id = %s ORDER BY time {order} LIMIT 1
            """).format(
                table=sql.Identifier(table),
                order=order,
            )

            with self._connection.cursor() as cur:
                cur.execute(stmt, (series_id,))
                row = cur.fetchone()
                if not row:
                    return Result.ok_payload(None)

                sid, time, open, high, low, close, volume = row

                return Result.ok_payload(
                    SeriesPoint(
                        series_id=sid,
                        time=time,
                        open=open,
                        high=high,
                        low=low,
                        close=close,
                        volume=volume,
                    )
                )

        return self._database_operation(operation, context)

    # ------------------------------------------------------------
    # Persisting assets and series
    # ------------------------------------------------------------

    def refresh_short_lived_series_ids(self) -> Result:
        """
        Load all short lived series IDs wi into a set for fast lookup during state rebuild.
        """
        sql = f"SELECT id FROM series WHERE retention = '{Retention.SHORT_LIVED}';"

        def operation() -> Result:
            rows = self._execute_read(sql)
            self._short_lived_series_ids = {row[0] for row in rows}
            return Result.ok_payload(None)

        return self._database_operation(operation, "load short lived series ids")

    def store_asset(self, asset: Asset) -> Result[Asset]:
        """
        Insert or update an asset row.
        YAML is authoritative, so we upsert on (symbol, provider).
        """

        base_fields = (
            asset.name,
            asset.symbol,
            asset.provider,
            asset.provider_code,
            asset.display_name,
            asset.instrument,
            asset.region,
            asset.exchange,
            asset.currency,
            asset.unit,
        )
        if asset.id is None:
            sql = """
                    INSERT INTO asset (name, symbol, provider, provider_code, display_name, instrument, region, exchange, currency, unit)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    RETURNING id;
                    """

            params = base_fields

        else:
            # UPDATE
            sql = """
                UPDATE asset
                SET name=%s, symbol=%s, provider=%s, provider_code=%s, display_name=%s, instrument=%s, region=%s, exchange=%s, currency=%s, unit=%s
                WHERE id=%s
                RETURNING id;
            """

            params = (*base_fields, asset.id)

        result = self._execute_write(sql, params)

        if not result.ok:
            return result
        return Result.ok_payload(asset if asset.id is not None else asset.with_id(result.payload))

    def store_series(self, series: Series) -> Result[Series]:
        """
        Insert or update a series row.
        YAML is authoritative, so we upsert on (asset_id, resolution).
        """
        if series.asset_id is None:
            return Result.fail("Store series failed", "asset_id was not set")

        base_fields = (
            series.code,
            series.asset_id,
            series.interval,
            series.series_type,
            series.retention,
            series.bootstrap_history,
            series.completion_policy,
        )

        if series.id is None:
            # INSERT
            sql = """
                INSERT INTO series (code, asset_id, interval, series_type, retention, bootstrap_history, completion_policy)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                RETURNING id;
            """
            params = base_fields

        else:
            # UPDATE
            sql = """
                UPDATE series SET code=%s, asset_id=%s, interval=%s, series_type=%s, retention=%s, bootstrap_history=%s, completion_policy=%s WHERE id=%s RETURNING id;
            """

            params = (*base_fields, series.id)

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
                    SELECT s.id, s.code, s.asset_id, a.name as asset_name, a.name || ':' || s.code AS name,
                           s.interval, s.series_type, s.retention, s.bootstrap_history, s.completion_policy FROM series s
                    JOIN asset a ON s.asset_id = a.id
                    ORDER BY s.id;
                    """
                )
                rows = cursor.fetchall()

            return Result.ok_payload(
                [
                    Series(
                        id=row[0],
                        code=row[1],
                        asset_id=row[2],
                        asset_name=row[3],
                        name=row[4],
                        interval=row[5],
                        series_type=row[6],
                        retention=row[7],
                        bootstrap_history=row[8],
                        completion_policy=row[9],
                    )
                    for row in rows
                ]
            )

        return self._database_operation(operation, "get_series")
