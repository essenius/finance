# Copyright 2026 Rik Essenius
# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.
# File: tests/state/conftest.py

from datetime import UTC, datetime

import pytest

from finance.common.model import Series, SeriesPoint

# state_env is defined in the parent folder's conftest.py


@pytest.fixture()
def make_entry(make_asset, make_series) -> dict:
    def _make(series_id=1, value=1, timestamp: int = 600, name="spx"):
        time = datetime.fromtimestamp(timestamp, tz=UTC)
        asset = make_asset(id=series_id, name=name)
        series = make_series(asset, id=series_id)
        return {"series": series, "point": SeriesPoint(series_id=series_id, time=time, close=value)}

    return _make


@pytest.fixture
def two_wal_entries(make_entry) -> list[tuple[Series, SeriesPoint] | None]:
    def _entries():
        return [
            make_entry(series_id=1, value=1, timestamp=10),
            make_entry(series_id=1, value=2, timestamp=20),
        ]

    return _entries


@pytest.fixture
def two_wal_entries_with_none(make_entry) -> list[tuple[Series, SeriesPoint] | None]:
    def _entries():
        return [
            make_entry(series_id=1, value=1, timestamp=10),
            make_entry(series_id=1, value=2, timestamp=20),
            None,
        ]

    return _entries
