# Copyright 2026 Rik Essenius
# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.
# File: tests/timeseries/conftest.py

from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest

from finance.common.model import SeriesPoint
from finance.common.string_enums import Retention
from finance.timeseries.series_backend import SeriesBackend, TimescaleConfig
from finance.timeseries.timescale_sql import TimescaleSqlClient


class FakeClock:
    def __init__(self):
        self.t = datetime(2025, 6, 15, 15, 6, 40, tzinfo=UTC)

    def __call__(self):
        return self.t

    def advance(self, dt):
        self.t += timedelta(seconds=dt)


class FakeConnection:
    closed: bool = False


@pytest.fixture
def sql_with_fake_connection(make_backend_config):
    def _make(connected: bool = True, **kwargs):

        config = make_backend_config()
        sql = TimescaleSqlClient(config)
        sql._connection = MagicMock()
        sql._connection.closed = not connected

        sql.mock_cursor = MagicMock()
        fetch_one = kwargs.get("fetchone")
        sql.mock_cursor.fetchone.return_value = fetch_one
        fetch_all = kwargs.get("fetchall")
        sql.mock_cursor.fetchall.return_value = fetch_all
        execute = kwargs.get("execute")
        sql.mock_cursor.execute.return_value = execute
        sql._connection.cursor.return_value.__enter__.return_value = sql.mock_cursor
        return sql, sql.mock_cursor

    return _make


@pytest.fixture
def sql_with_fake_psycopg(make_backend_config):
    @contextmanager
    def _sql_with_fake_psycopg(execute_error=False):
        config = make_backend_config()

        fake_cursor = MagicMock()
        fake_cursor.execute.return_value = None
        fake_cursor.executemany.return_value = None

        fake_conn = MagicMock()
        fake_conn.closed = False
        fake_conn.cursor.return_value.__enter__.return_value = fake_cursor
        fake_conn.cursor.return_value.__exit__.return_value = False
        fake_conn.cursor.return_value.execute = fake_cursor.execute
        fake_conn.cursor.return_value.fetchone = fake_cursor.fetchone
        fake_conn.cursor.return_value.fetchall = fake_cursor.fetchall

        if execute_error:
            fake_cursor.execute.side_effect = Exception("Execute boom!")

        with patch("psycopg.connect", return_value=fake_conn) as mock_connect:
            sql = TimescaleSqlClient(config)

            sql.mock_connect = mock_connect
            sql.mock_conn = fake_conn
            sql.mock_cursor = fake_cursor

            yield sql

    return _sql_with_fake_psycopg


@pytest.fixture
def make_backend_config():
    def _make(max_batch_size: int = 2, max_batch_age_seconds: int = 2):
        return TimescaleConfig(
            host="x",
            dbname="finance",
            user="u",
            password="p",
            max_batch_size=max_batch_size,
            max_batch_age=timedelta(seconds=max_batch_age_seconds),
        )

    return _make


@pytest.fixture
def make_backend(make_backend_config, sql_with_fake_connection):
    def _make(max_batch_size: int = 2, max_batch_age_seconds: int = 2, connected: bool = True, **kwargs):
        cfg = make_backend_config(max_batch_size=max_batch_size, max_batch_age_seconds=max_batch_age_seconds)

        sql_client, _ = sql_with_fake_connection(connected=connected, **kwargs)

        backend = SeriesBackend(config=cfg, sql_client=sql_client, now=FakeClock())

        return backend

    return _make


@pytest.fixture
def make_entry():
    def _make(id=1, fields=None, retention=Retention.DAILY, timestamp=0):
        return SeriesPoint(series_id=id, time=timestamp, retention=retention, fields=fields or {})

    return _make


@pytest.fixture
def make_entries(make_entry):
    def _make(n):
        return [make_entry(fields={"v": i}, timestamp=i) for i in range(n)]

    return _make


"""
@pytest.fixture
def unwrapped_backend(make_backend_context):
    @contextmanager
    def _unwrapped_backend(config, execute_error=False):
        with make_backend_context(config, execute_error) as result:
            yield result.payload

    return _unwrapped_backend
"""
