# Copyright 2026 Rik Essenius
# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.
# File: src/finance/timeseries/timescale_sql.py

from __future__ import annotations

import contextlib
from collections.abc import Callable
from typing import LiteralString

# using direct import to facilitate patching
import psycopg
from psycopg.abc import QueryNoTemplate
from psycopg.sql import SQL, Identifier

from ..common.configuration import TimescaleConfig
from ..common.guards import require
from ..common.types import Failure, ParseError, Result, Success
from .backend_protocol import SqlReadPayload


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

    def execute_many(
        self, query: LiteralString, params: list[tuple], *, table: str | None = None, context: str
    ) -> Result[None]:
        return self._database_operation(lambda cur: cur.executemany(self._resolve_query(query, table), params), context)

    def is_connected(self) -> bool:
        conn = self._connection
        return conn is not None and not conn.closed

    def execute_read(
        self, query: LiteralString, params: tuple | None = None, *, table: str | None = None, context: str = "Read"
    ) -> Result[SqlReadPayload]:
        def operation(cursor: psycopg.Cursor) -> SqlReadPayload:
            cursor.execute(self._resolve_query(query, table), params or ())
            rows = cursor.fetchall()
            if cursor.description is None:
                raise ParseError("Query result does not contain column names")
            columns = {desc.name: i for i, desc in enumerate(cursor.description)}
            return {"rows": rows, "columns": columns}

        return self._database_operation(operation, context)

    def execute_write(
        self, query: LiteralString, params: tuple, *, table: str | None = None, context: str = "Write"
    ) -> Result[int]:
        def operation(cursor: psycopg.Cursor) -> int:
            cursor.execute(self._resolve_query(query, table), params)
            row = cursor.fetchone()
            if row is None:
                raise ParseError("Query did not return a result")
            return row[0]

        return self._database_operation(operation, context)

    # ---  Private methods ---

    def _connect(self):
        return psycopg.connect(**(self._config.connect_config()))

    def _database_operation[T](self, fn: Callable[[psycopg.Cursor], T], context: str = "Database") -> Result[T]:
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

        except psycopg.Error as exc:
            # Roll back aborted transaction state
            with contextlib.suppress(Exception):
                connection.rollback()
            return Failure(reason=f"{context} operation failed", error=exc)

        except ParseError as exc:
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

    def _resolve_query(self, query: LiteralString, table: str | None) -> QueryNoTemplate:
        if table is None:
            return SQL(query)
        if "{table}" not in query:
            raise ParseError("table parameter supplied, but query contains no {table} placeholder")
        return SQL(query).format(table=Identifier(table))
