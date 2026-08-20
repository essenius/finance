# Copyright 2026 Rik Essenius
# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.
# File: tests/test_orchestrator.py

from datetime import UTC, datetime
from unittest.mock import Mock, call

import pytest

from finance.common.model import FetchData, FetchResult, SeriesPoint, SeriesResult, SeriesState
from finance.common.result import Result
from finance.orchestrator import Orchestrator, unwrap


def ok_fetch_result(points: list) -> FetchResult:
    return FetchResult.ok_payload(FetchData(series_id=1, points=points, metadata=None))


# ---------------------------------------------------------------------------
# unwrap tests
# ---------------------------------------------------------------------------


def test_unwrap_success_no_warning(json_caplog):
    json_caplog.set_level("DEBUG")
    r = Result.ok_payload(123)
    assert unwrap(r, throw=False) == 123
    # no warnings logged
    assert "warnings=" not in json_caplog.text


def test_unwrap_success_with_warning(json_caplog):
    json_caplog.set_level("WARNING")
    r = Result(ok=True, payload=42, warnings=["careful"])
    assert unwrap(r, throw=False) == 42
    assert '"warnings": ["careful"]}' in json_caplog.text


def test_unwrap_failure_no_throw(json_caplog):
    json_caplog.set_level("ERROR")
    r = Result.fail("x", "broken")
    assert unwrap(r, throw=False) is None
    assert '"reason": "x", "error": "broken"}' in json_caplog.text


def test_unwrap_failure_with_throw():
    r = Result.fail("x", "boom")
    with pytest.raises(ValueError):
        unwrap(r, throw=True)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class FakeState:
    """State that records ingest calls."""

    def __init__(self):
        self.calls = []
        self.series = {}

    def ingest(self, point: SeriesPoint):
        self.calls.append(point)
        return SeriesResult.ok_payload("spx", point)  # success

    def update_state(self, series_id: int, first: int, last: int) -> None:
        self.series[series_id] = SeriesState(first_point=first, last_point=last)


class SkipState(FakeState):
    """State that returns skip (payload=None)."""

    def ingest(self, point: SeriesPoint):
        self.calls.append(point)
        return SeriesResult.ok_payload("spx", None)  # skip


class FailingState(FakeState):
    """State that returns failure."""

    def ingest(self, point: SeriesPoint):
        self.calls.append(point)
        return SeriesResult.fail("spx", "ingest failed")


def make_result(payload=None, *, ok=True, reason=None, error=None, warnings=None):
    warnings_real = warnings or []
    if ok:
        return Result.ok_payload(payload, warnings_real)
    return Result.fail(reason=reason, error=error, warnings=warnings_real)


@pytest.fixture
def backend():
    return Mock()


@pytest.fixture
def registry():
    return Mock()


@pytest.fixture
def state():
    state = Mock()
    state.series = {}
    return state


@pytest.fixture
def fetcher():
    return Mock()


@pytest.fixture
def orchestrator(backend, registry, state, fetcher):
    return Orchestrator(backend=backend, registry=registry, state=state, fetcher=fetcher)


def test_prepare_loads_state_and_reconciles_backend(orchestrator, backend, registry, state):
    asset = Mock(name="asset")
    stored_asset = Mock(name="stored_asset")
    series = Mock(name="series")
    stored_series = Mock(name="stored_series")

    state.load.return_value = make_result(3)
    backend.get_assets.return_value = make_result([asset])
    registry.merge_and_find_new_assets.return_value = [asset]
    backend.store_asset.return_value = make_result(stored_asset)

    backend.get_series.return_value = make_result([series])

    reconciled = Mock()
    reconciled.to_persist = [series]
    registry.reconcile_series.return_value = reconciled
    backend.store_series.return_value = make_result(stored_series)

    orchestrator.prepare()

    state.load.assert_called_once_with()
    backend.get_assets.assert_called_once_with()
    registry.merge_and_find_new_assets.assert_called_once_with([asset])

    backend.store_asset.assert_called_once_with(asset)
    registry.register_stored_asset.assert_called_once_with(stored_asset)

    backend.get_series.assert_called_once_with()
    registry.reconcile_series.assert_called_once_with([series])

    backend.store_series.assert_called_once_with(series)
    registry.register_stored_series.assert_called_once_with(stored_series)

    backend.refresh_short_lived_series_ids.assert_called_once_with()


def test_prepare_does_not_persist_when_nothing_changed(orchestrator, backend, registry, state):
    state.load.return_value = make_result(0)
    backend.get_assets.return_value = make_result([])
    registry.merge_and_find_new_assets.return_value = []

    backend.get_series.return_value = make_result([])

    reconciled = Mock()
    reconciled.to_persist = []
    registry.reconcile_series.return_value = reconciled

    orchestrator.prepare()

    backend.store_asset.assert_not_called()
    backend.store_series.assert_not_called()
    registry.register_stored_asset.assert_not_called()
    registry.register_stored_series.assert_not_called()
    backend.refresh_short_lived_series_ids.assert_called_once_with()


def test_prepare_continues_when_wal_load_fails(orchestrator, backend, registry, state):
    state.load.return_value = make_result(None, ok=False, reason="WAL error")

    backend.get_assets.return_value = make_result([])
    registry.merge_and_find_new_assets.return_value = []
    backend.get_series.return_value = make_result([])

    reconciled = Mock()
    reconciled.to_persist = []
    registry.reconcile_series.return_value = reconciled

    orchestrator.prepare()

    backend.get_assets.assert_called_once_with()
    backend.get_series.assert_called_once_with()


def test_ingest_points_ingests_all_points_and_updates_range(orchestrator, state):
    series = Mock()
    series.id = 42
    series.name = "TEST"

    first = Mock()
    first.time = datetime(2026, 8, 20, 10, tzinfo=UTC)
    first.series_id = 42

    second = Mock()
    second.time = datetime(2026, 8, 20, 11, tzinfo=UTC)
    second.series_id = 42

    points = [first, second]

    state.ingest.return_value = make_result(None)

    stored_range = Mock()
    stored_range.first_point = first.time
    stored_range.last_point = second.time
    state.series[42] = stored_range

    result = orchestrator.ingest_points(points, series)

    assert result is True
    assert state.ingest.call_args_list == [
        ((first,), {}),
        ((second,), {}),
    ]
    state.update_state.assert_called_once_with(
        42,
        first.time,
        second.time,
    )


def test_ingest_points_uses_lowest_and_highest_timestamp(orchestrator, state):
    series = Mock()
    series.id = 42
    series.name = "TEST"

    early = Mock()
    early.time = datetime(2026, 8, 20, 10, tzinfo=UTC)
    early.series_id = 42

    late = Mock()
    late.time = datetime(2026, 8, 20, 12, tzinfo=UTC)
    late.series_id = 42

    state.ingest.return_value = make_result(None)

    stored_range = Mock()
    stored_range.first_point = early.time
    stored_range.last_point = late.time
    state.series[42] = stored_range

    result = orchestrator.ingest_points([late, early], series)

    assert result is True
    state.update_state.assert_called_once_with(
        42,
        early.time,
        late.time,
    )


def test_ingest_points_does_not_update_range_when_point_ingestion_fails(orchestrator, state):
    series = Mock()
    series.id = 42
    series.name = "TEST"

    points = []

    for hour in (10, 11, 12):
        point = Mock()
        point.time = datetime(2026, 8, 20, hour, tzinfo=UTC)
        point.series_id = 42
        points.append(point)

    state.ingest.side_effect = [
        make_result(None),
        make_result(None, ok=False, reason="database error"),
        make_result(None),
    ]

    result = orchestrator.ingest_points(points, series)

    assert result is False
    assert state.ingest.call_count == 3
    state.update_state.assert_not_called()


def test_handle_fetch_response_returns_false_for_failed_fetch(orchestrator, registry, backend):
    result = FetchResult(
        ok=False,
        payload=None,
        reason="fetch failed",
        error="connection error",
        warnings=[],
    )

    assert orchestrator.handle_fetch_response(result) is False

    registry.get_series_by_id.assert_not_called()
    backend.store_asset.assert_not_called()


def test_handle_fetch_response_ingests_points_without_metadata(orchestrator, registry):
    series = Mock()
    series.id = 42
    series.name = "TEST"

    point = Mock()
    point.time = datetime(2026, 8, 20, 10, tzinfo=UTC)
    point.series_id = series.id

    result = FetchResult(
        ok=True,
        payload=Mock(metadata=None, points=[point], series_id=series.id),
        reason=None,
        error=None,
        warnings=[],
    )

    registry.get_series_by_id.return_value = series

    orchestrator.ingest_points = Mock(return_value=True)

    assert orchestrator.handle_fetch_response(result) is True

    registry.get_series_by_id.assert_called_once_with(42)
    orchestrator.ingest_points.assert_called_once_with([point], series)
    registry.register_provider_metadata.assert_not_called()


def test_handle_fetch_response_registers_provider_metadata_without_persisting(orchestrator, registry):
    series = Mock()
    series.asset_id = 123

    metadata = Mock()

    result = FetchResult(
        ok=True,
        payload=Mock(metadata=metadata, points=[]),
        reason=None,
        error=None,
        warnings=[],
    )

    registry.get_series_by_id.return_value = series
    registry.register_provider_metadata.return_value = None

    assert orchestrator.handle_fetch_response(result) is True

    registry.register_provider_metadata.assert_called_once_with(
        123,
        metadata,
    )
    orchestrator.backend.store_asset.assert_not_called()


def test_handle_fetch_response_persists_changed_asset_metadata(orchestrator, registry, backend):
    series = Mock()
    series.asset_id = 123

    metadata = Mock()
    asset = Mock()
    stored_asset = Mock()

    result = FetchResult(
        ok=True,
        payload=Mock(metadata=metadata, points=[]),
        reason=None,
        error=None,
        warnings=[],
    )

    registry.get_series_by_id.return_value = series
    registry.register_provider_metadata.return_value = asset
    backend.store_asset.return_value = make_result(stored_asset)

    assert orchestrator.handle_fetch_response(result) is True

    registry.register_provider_metadata.assert_called_once_with(123, metadata)
    backend.store_asset.assert_called_once_with(asset)

    # This should be register_stored_asset(), not register_stored_series().
    registry.register_stored_asset.assert_called_once_with(stored_asset)


def test_handle_fetch_response_processes_metadata_and_points(orchestrator, registry):
    series = Mock()
    series.asset_id = 123

    metadata = Mock()
    point = Mock()

    result = FetchResult(
        ok=True,
        payload=Mock(metadata=metadata, points=[point]),
        reason=None,
        error=None,
        warnings=[],
    )

    registry.get_series_by_id.return_value = series
    registry.register_provider_metadata.return_value = None

    orchestrator.ingest_points = Mock(return_value=True)

    assert orchestrator.handle_fetch_response(result) is True

    registry.register_provider_metadata.assert_called_once_with(123, metadata)
    orchestrator.ingest_points.assert_called_once_with([point], series)


def test_handle_fetch_response_with_no_points_does_not_ingest(orchestrator, registry):
    series = Mock()
    series.asset_id = 123

    result = FetchResult(
        ok=True,
        payload=Mock(metadata=None, points=[]),
        reason=None,
        error=None,
        warnings=[],
    )

    registry.get_series_by_id.return_value = series

    assert orchestrator.handle_fetch_response(result) is True

    orchestrator.ingest_points = Mock()
    orchestrator.ingest_points.assert_not_called()


def test_finalize_saves_state_and_returns_zero_on_success(orchestrator, state):
    assert orchestrator.finalize(0) == 0

    state.save.assert_called_once_with()


def test_finalize_saves_state_and_returns_one_when_fetches_failed(orchestrator, state):
    assert orchestrator.finalize(3) == 1

    state.save.assert_called_once_with()


def test_run_prepares_processes_fetches_and_finalizes(orchestrator, fetcher):
    orchestrator.prepare = Mock()
    orchestrator.handle_fetch_response = Mock(return_value=True)
    orchestrator.finalize = Mock(return_value=0)

    result1 = Mock()
    result2 = Mock()

    fetcher.fetch_incrementally.return_value = [result1, result2]

    assert orchestrator.run() == 0

    orchestrator.prepare.assert_called_once_with()
    fetcher.fetch_incrementally.assert_called_once_with(orchestrator.state)

    assert orchestrator.handle_fetch_response.call_args_list == [
        ((result1,), {}),
        ((result2,), {}),
    ]

    orchestrator.finalize.assert_called_once_with(0)


def test_run_counts_failed_fetch_responses(orchestrator, fetcher):
    orchestrator.prepare = Mock()
    orchestrator.handle_fetch_response = Mock(side_effect=[True, False, False, True])
    orchestrator.finalize = Mock(return_value=1)

    results = [Mock(), Mock(), Mock(), Mock()]
    fetcher.fetch_incrementally.return_value = results

    assert orchestrator.run() == 1

    orchestrator.prepare.assert_called_once_with()
    orchestrator.handle_fetch_response.assert_has_calls([call(result) for result in results])
    orchestrator.finalize.assert_called_once_with(2)


def test_run_finalizes_successfully_when_nothing_is_fetched(orchestrator, fetcher):
    orchestrator.prepare = Mock()
    orchestrator.handle_fetch_response = Mock()
    orchestrator.finalize = Mock(return_value=0)

    fetcher.fetch_incrementally.return_value = []

    assert orchestrator.run() == 0

    orchestrator.handle_fetch_response.assert_not_called()
    orchestrator.finalize.assert_called_once_with(0)


"""

def test_process_result_failure_result_not_ok():
    r = FetchResult.fail("spx", "network")
    state = FakeState()
    ok = process_result(r, state, Mock())
    assert ok is False
    assert state.calls == []


def test_process_result_empty_payload():
    r = ok_fetch_result([])
    state = FakeState()
    ok = process_result(r, state, Mock())
    assert ok is True
    assert state.calls == []


def test_process_result_single_point(fixed_now):
    now = fixed_now()
    r = ok_fetch_result([SeriesPoint(series_id=1, time=now, close=1)])
    state = FakeState()

    ok = process_result(r, state, Mock())
    assert ok is True

    assert len(state.calls) == 1
    point: SeriesPoint = state.calls[0]
    assert point.series_id == 1
    assert point.close == 1
    assert point.time == now


def test_process_result_multiple_points(fixed_now):
    now = fixed_now()
    fp1 = SeriesPoint(series_id=1, time=now + timedelta(seconds=5), close=1)
    fp2 = SeriesPoint(series_id=2, time=now, close=2)
    r = ok_fetch_result([fp1, fp2])
    state = FakeState()

    ok = process_result(r, state, Mock())
    assert ok is True
    assert len(state.calls) == 2

    assert state.calls[0].close == 1
    assert state.calls[1].close == 2


def test_process_result_skip(fixed_now):
    fp = SeriesPoint(series_id=1, time=fixed_now(), close=1)
    r = ok_fetch_result([fp])
    state = SkipState()

    ok = process_result(r, state, Mock())
    assert ok is True
    assert len(state.calls) == 1


def test_process_result_ingest_failure(fixed_now):
    fp = SeriesPoint(series_id=1, time=fixed_now(), close=1)
    r = ok_fetch_result([fp])
    state = FailingState()

    ok = process_result(r, state, Mock())
    assert ok is False
    assert len(state.calls) == 1


def test_reconcile_registry(make_asset, make_series, make_metadata):
    registry = Registry()
    meta_stock = make_metadata(instrument="stock")
    asset = make_asset("SPX", id=None, config_metadata=meta_stock)
    registry.load_yaml_assets([asset])
    series = make_series(asset, retention=Retention.SHORT_LIVED, id=None, interval="1h")
    registry.load_yaml_series([series])
    backend = MagicMock()

    meta_forex = make_metadata(instrument="forex")
    old_asset = make_asset("SPX", id=1, config_metadata=meta_forex)
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
"""
