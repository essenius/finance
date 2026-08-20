# Copyright 2026 Rik Essenius
# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.
# File: tests/state/conftest.py

from datetime import UTC, datetime

import pytest

from finance.common.model import Series, SeriesPoint
from tests.support.types import ConfigurableFactory, Factory


@pytest.fixture()
def make_entry(
    make_asset: ConfigurableFactory, make_series: ConfigurableFactory
) -> ConfigurableFactory[dict[str, Series | SeriesPoint]]:
    def _make(
        series_id: int = 1, value: float = 1, timestamp: int = 600, name: str = "spx"
    ) -> dict[str, Series | SeriesPoint]:
        timestamp_utc = datetime.fromtimestamp(timestamp, tz=UTC)
        asset = make_asset(id=series_id, name=name)
        series = make_series(asset, id=series_id)
        return {"point": SeriesPoint(series_id=series_id, time=timestamp_utc, close=value), "series": series}

    return _make


@pytest.fixture
def two_wal_entries(make_entry: ConfigurableFactory) -> Factory[list[SeriesPoint]]:
    def _entries() -> list[SeriesPoint]:
        return [
            make_entry(series_id=1, value=1, timestamp=10)["point"],
            make_entry(series_id=1, value=2, timestamp=20)["point"],
        ]

    return _entries
