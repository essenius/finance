# Copyright 2026 Rik Essenius
# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.
# File: tests/test_main_utils.py

from unittest.mock import MagicMock, Mock

import pytest

from finance.common.model import FetchResult, Result, Retention, Series, SeriesPoint, SeriesResult
from finance.main_utils import process_result, reconcile_registry, unwrap
from finance.registry.registry import Registry

# ---------------------------------------------------------------------------
# unwrap tests
# ---------------------------------------------------------------------------


def test_unwrap_success_no_warning(caplog):
    caplog.set_level("DEBUG")
    r = Result.ok_payload(123)
    assert unwrap(r, throw=False) == 123
    # no warnings logged
    assert "warnings=" not in caplog.text


def test_unwrap_success_with_warning(caplog):
    caplog.set_level("WARNING")
    r = Result(ok=True, payload=42, warnings=["careful"])
    assert unwrap(r, throw=False) == 42
    assert "warnings=careful" in caplog.text


def test_unwrap_failure_no_throw(caplog):
    caplog.set_level("ERROR")
    r = Result.fail("x", "broken")
    assert unwrap(r, throw=False) is None
    assert "reason=x | error=broken" in caplog.text


def test_unwrap_failure_with_throw():
    r = Result.fail("x", "boom")
    with pytest.raises(ValueError):
        unwrap(r, throw=True)


# ---------------------------------------------------------------------------
# process_result tests
# ---------------------------------------------------------------------------


class FakeState:
    """State that records ingest calls."""

    def __init__(self):
        self.calls = []

    def ingest(self, series: Series, point: SeriesPoint):
        self.calls.append(point)
        return SeriesResult.ok_payload("spx", point)  # success

    def update_range(self, series_id: int, first: int, last: int) -> None:
        pass


class SkipState(FakeState):
    """State that returns skip (payload=None)."""

    def ingest(self, series: Series, point: SeriesPoint):
        self.calls.append(point)
        return SeriesResult.ok_payload("spx", None)  # skip


class FailingState(FakeState):
    """State that returns failure."""

    def ingest(self, series: Series, point: SeriesPoint):
        self.calls.append(point)
        return SeriesResult.fail("spx", "ingest failed")


def test_process_result_failure_result_not_ok():
    r = FetchResult.fail("spx", "network")
    state = FakeState()
    ok = process_result(r, state, Mock())
    assert ok is False
    assert state.calls == []


def test_process_result_empty_payload():
    r = FetchResult.ok_payload("spx", [])
    state = FakeState()
    ok = process_result(r, state, Mock())
    assert ok is True
    assert state.calls == []


def test_process_result_single_point():
    fp = SeriesPoint(series_id=1, time=100, close=1)
    r = FetchResult.ok_payload("spx", [fp])
    state = FakeState()

    ok = process_result(r, state, Mock())
    assert ok is True

    assert len(state.calls) == 1
    point: SeriesPoint = state.calls[0]
    assert point.series_id == 1
    assert point.close == 1
    assert point.time == 100


def test_process_result_multiple_points():
    fp1 = SeriesPoint(series_id=1, time=10, close=1)
    fp2 = SeriesPoint(series_id=2, time=20, close=2)
    r = FetchResult.ok_payload("spx", [fp1, fp2])
    state = FakeState()

    ok = process_result(r, state, Mock())
    assert ok is True
    assert len(state.calls) == 2

    assert state.calls[0].close == 1
    assert state.calls[1].close == 2


def test_process_result_skip():
    fp = SeriesPoint(series_id=1, time=100, close=1)
    r = FetchResult.ok_payload("spx", [fp])
    state = SkipState()

    ok = process_result(r, state, Mock())
    assert ok is True
    assert len(state.calls) == 1


def test_process_result_ingest_failure():
    fp = SeriesPoint(series_id=1, time=100, close=1)
    r = FetchResult.ok_payload("spx", [fp])
    state = FailingState()

    ok = process_result(r, state, Mock())
    assert ok is False
    assert len(state.calls) == 1


def test_reconcile_registry(make_asset, make_series):
    registry = Registry()
    asset = make_asset("SPX", id=None, instrument="stock")
    registry.load_yaml_assets([asset])
    series = make_series(asset, retention=Retention.SHORT_LIVED, id=None, interval="1h")
    registry.load_yaml_series([series])
    backend = MagicMock()

    old_asset = make_asset("SPX", id=1, instrument="forex")
    old_series = make_series(asset, retention=Retention.SHORT_LIVED, id=2, interval="2h")

    new_asset = asset.with_id(1)
    new_series = series.with_id(2)

    backend.get_assets.return_value = Result.ok_payload([old_asset])
    backend.get_series.return_value = Result.ok_payload([old_series])
    backend.store_asset.return_value = Result.ok_payload(new_asset)
    backend.store_series.return_value = Result.ok_payload(new_series)
    backend.refresh_short_lived_series_ids.return_value = None

    reconcile_registry(registry, backend)

    assert registry.all_assets() == [new_asset]
    assert registry.all_series() == [new_series]
    assert backend.refresh_short_lived_series_ids.call_count == 1
