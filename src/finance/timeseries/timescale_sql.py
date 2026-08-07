# Copyright 2026 Rik Essenius
# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.
# File: src/finance/timeseries/timescale_sql.py

from __future__ import annotations

import contextlib
from dataclasses import dataclass
from datetime import timedelta

import psycopg
from psycopg import sql

from ..common.result import Result


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


class TimescaleSqlClient:
    def __init__(self, config: TimescaleConfig):
        self._config = config
        self._connection = None

    # --- Public methods ---

    def close_connection(self) -> None:
        if self._connection is not None:
            with contextlib.suppress(Exception):
                self._connection.close()
        self._connection = None

    def execute_read(self, sql_query: str, params: tuple | None = None, context: str = "Read") -> Result:
        def operation(cursor):
            cursor.execute(sql_query, params or ())
            rows = cursor.fetchall()
            columns = {desc.name: i for i, desc in enumerate(cursor.description)}
            return {"rows": rows, "columns": columns}

        return self._database_operation(operation, context)

    def execute_write(self, query: str, params: tuple, context: str = "Write") -> Result[int]:
        return self._database_operation(
            lambda cursor: (cursor.execute(query, params), cursor.fetchone()[0])[1], context
        )

        # lambda: Result.ok_payload(self._execute_write(sql_query, params)), "write")

    def execute_many(self, query: str | sql.SQL, params: list[tuple], context: str) -> Result[None]:
        return self._database_operation(lambda cur: cur.executemany(query, params), context)
        # lambda: Result.ok_payload(self._execute_many(sql_query, params, context)), context

    def is_connected(self) -> bool:
        conn = self._connection
        return conn is not None and not conn.closed

    # ---  Private methods ---

    def _connect(self):
        return psycopg.connect(**(self._config.connect_config()))

    def _database_operation(self, fn, context: str = "Database") -> Result:
        ensure = self._ensure_connected()
        if not ensure.ok:
            return ensure

        try:
            with self._connection.cursor() as cursor:
                result = fn(cursor)

            # Commit only if fn succeeded
            self._connection.commit()
            return Result.ok_payload(result)

        except Exception as exc:
            # Roll back aborted transaction state
            with contextlib.suppress(Exception):
                self._connection.rollback()

            return Result.fail(f"{context} operation failed", exc)

    def _ensure_connected(self) -> Result[None]:
        if self.is_connected():
            return Result.ok_payload(None)

        try:
            conn = self._connect()
        except Exception as exc:
            return Result.fail("Connect failed", exc)

        try:
            with conn.cursor() as cur:
                cur.execute("SELECT id from series LIMIT 1")
        except Exception as exc:
            conn.rollback()
            return Result.fail("Database startup failed", exc)

        self._connection = conn
        return Result.ok_payload(None)
