# Copyright 2026 Rik Essenius
# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.
# File: tests/timeseries/conftest.py

from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, Mock, patch

import pytest

from finance.common.model import Series, SeriesPoint
from finance.common.string_enums import Retention
from finance.timeseries.timescale_backend import TimescaleBackend, TimescaleConfig


@pytest.fixture
def session():
    return Mock()


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
def make_backend():
    def _make(max_batch_size: int = 2, max_batch_age_seconds: int = 2):
        cfg = TimescaleConfig(
            host="x",
            dbname="finance",
            user="u",
            password="p",
            max_batch_size=max_batch_size,
            max_batch_age=timedelta(seconds=max_batch_age_seconds),
        )

        def series_by_id(id: int):
            return None

        backend = TimescaleBackend(cfg, series_by_id, now=FakeClock())
        backend._connection = MagicMock()
        # make it connected
        backend._connection.closed = False

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


@pytest.fixture
def make_backend_context():
    def series_by_id(id: int) -> Series:
        return None

    @contextmanager
    def _make_backend(config, execute_error=False):  # returns Result[TimescaleBackend]
        fake_cursor = MagicMock()
        fake_cursor.execute.return_value = None

        fake_conn = MagicMock()
        fake_conn.cursor.return_value.__enter__.return_value = fake_cursor

        if execute_error:
            fake_cursor.execute.side_effect = Exception("Execute boom!")

        with patch("psycopg.connect", return_value=fake_conn) as mock_connect:
            result = TimescaleBackend.from_config(config, series_by_id)

            if result.ok:
                backend = result.payload
                backend.mock_connect = mock_connect
                backend.mock_conn = fake_conn
                backend.mock_cursor = fake_cursor

            yield result

    return _make_backend


@pytest.fixture
def unwrapped_backend(make_backend_context):
    @contextmanager
    def _unwrapped_backend(config, execute_error=False):
        with make_backend_context(config, execute_error) as result:
            yield result.payload

    return _unwrapped_backend
