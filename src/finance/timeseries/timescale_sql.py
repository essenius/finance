# Copyright 2026 Rik Essenius
# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.
# File: src/finance/timeseries/timescale_sql.py

from __future__ import annotations

import contextlib

import psycopg

from finance.timeseries.backend_protocol import SqlReadPayload

from ..common.configuration import TimescaleConfig
from ..common.guards import require
from ..common.types import Failure, Result, Success


class TimescaleSqlClient:
    def __init__(self, config: TimescaleConfig):
        self._config = config
        self._connection: psycopg.Connection | None = None

    # --- Public methods ---

    def close_connection(self) -> None:
        if self._connection is not None:
            with contextlib.suppress(Exception):
                self._connection.close()
        self._connection = None

    def execute_read(self, query: str, params: tuple | None = None, context: str = "Read") -> Result[SqlReadPayload]:
        def operation(cursor):
            cursor.execute(query, params or ())
            rows = cursor.fetchall()
            columns = {desc.name: i for i, desc in enumerate(cursor.description)}
            return {"rows": rows, "columns": columns}

        return self._database_operation(operation, context)

    def execute_write(self, query: str, params: tuple, context: str = "Write") -> Result[int]:
        return self._database_operation(
            lambda cursor: (cursor.execute(query, params), cursor.fetchone()[0])[1], context
        )

    def execute_many(self, query: str, params: list[tuple], context: str) -> Result[None]:
        return self._database_operation(lambda cur: cur.executemany(query, params), context)

    def is_connected(self) -> bool:
        conn = self._connection
        return conn is not None and not conn.closed

    # ---  Private methods ---

    def _connect(self):
        return psycopg.connect(**(self._config.connect_config()))

    def _database_operation(self, fn, context: str = "Database") -> Result:
        ensure = self._ensure_connected()
        if ensure.ok is False:
            return ensure

        connection = require(self._connection)
        try:
            with connection.cursor() as cursor:
                result = fn(cursor)

            # Commit only if fn succeeded
            connection.commit()
            return Success(result)

        except Exception as exc:
            # Roll back aborted transaction state
            with contextlib.suppress(Exception):
                connection.rollback()

            return Failure(reason=f"{context} operation failed", error=exc)

    def _ensure_connected(self) -> Result[None]:
        if self.is_connected():
            return Success(None)

        try:
            conn = self._connect()
        except Exception as exc:
            return Failure(reason="Connect failed", error=exc)

        try:
            with conn.cursor() as cur:
                cur.execute("SELECT id from series LIMIT 1")
        except Exception as exc:
            conn.rollback()
            return Failure(reason="Database startup failed", error=exc)

        self._connection = conn
        return Success(None)
