# Copyright 2026 Rik Essenius
# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.
# File: tests/timeseries/conftest.py

from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, Mock

import pytest

from finance.common.model import Resolution, SeriesPoint
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
            max_batch_age_seconds=max_batch_age_seconds,
        )
        backend = TimescaleBackend(cfg, FakeClock())
        backend._connection = MagicMock()
        # make it connected
        backend._connection.closed = False

        return backend

    return _make


@pytest.fixture
def make_entry():
    def _make(id=1, fields=None, resolution=Resolution.DAILY, timestamp=0):
        return SeriesPoint(series_id=id, timestamp=timestamp, resolution=resolution, fields=fields or {})

    return _make


@pytest.fixture
def make_entries(make_entry):
    def _make(n):
        return [make_entry(fields={"v": i}, timestamp=i) for i in range(n)]

    return _make
