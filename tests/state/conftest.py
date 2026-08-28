# Copyright 2026 Rik Essenius
# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.
# File: tests/state/conftest.py

from datetime import datetime

import pytest

from finance.common.model import Series, SeriesPoint, SeriesState
from finance.common.time_utils import UTC
from tests.support.types import Creator, Factory


@pytest.fixture()
def make_entry(make_asset: Creator, make_series: Creator) -> Creator[dict[str, Series | SeriesPoint]]:
    def _make(
        series_id: int = 1, value: float = 1, timestamp: int = 600, name: str = "spx"
    ) -> dict[str, Series | SeriesPoint]:
        timestamp_utc = datetime.fromtimestamp(timestamp, tz=UTC)
        asset = make_asset(id=series_id, name=name)
        series = make_series(asset, id=series_id)
        return {"point": SeriesPoint(series_id=series_id, time=timestamp_utc, close=value), "series": series}

    return _make


@pytest.fixture
def two_wal_entries(make_entry: Creator) -> Factory[list[SeriesPoint]]:
    def _entries() -> list[SeriesPoint]:
        return [
            make_entry(series_id=1, value=1, timestamp=10)["point"],
            make_entry(series_id=1, value=2, timestamp=20)["point"],
        ]

    return _entries


@pytest.fixture
def make_series_state(ts) -> Creator[SeriesState]:
    def _make(start: int = 0, end: int = 1200) -> SeriesState:
        return SeriesState(first_point=ts(start), last_point=ts(end))

    return _make
