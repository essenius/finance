# Copyright 2026 Rik Essenius
# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.
# File: tests/test_orchestrator.py

from datetime import datetime
from unittest.mock import Mock, call

import pytest
from pytest import LogCaptureFixture

from finance.common.asset_metadata import AssetMetadata
from finance.common.model import Asset, FetchData, SeriesPoint, SeriesState
from finance.common.time_utils import UTC
from finance.common.types import AppError, Failure, Success
from finance.orchestrator import Orchestrator, unwrap
from tests.support.types import Creator, Factory


@pytest.fixture
def asset() -> Mock:
    asset = Mock()
    asset.id = 123
    asset.name = "TST"
    return asset


@pytest.fixture
def series(asset: Factory[Asset]) -> Mock:
    series = Mock()
    series.id = 42
    series.asset = asset
    series.name = "TEST"
    return series


@pytest.fixture
def backend() -> Mock:
    return Mock()


@pytest.fixture
def registry() -> Mock:
    return Mock()


@pytest.fixture
def state() -> Mock:
    state = Mock()
    state.series_state = {}
    return state


@pytest.fixture
def fetcher() -> Mock:
    return Mock()


@pytest.fixture
def orchestrator(backend: Mock, registry: Mock, state: Mock, fetcher: Mock) -> Orchestrator:
    return Orchestrator(backend=backend, registry=registry, state=state, fetcher=fetcher)


# ---------------------------------------------------------------------------
# unwrap tests
# ---------------------------------------------------------------------------


def test_unwrap_success_no_warning(json_caplog: LogCaptureFixture):
    json_caplog.set_level("DEBUG")
    r = Success(123)
    assert unwrap(r, throw=False) == 123
    # no warnings logged
    assert "warnings=" not in json_caplog.text


def test_unwrap_success_with_warning(json_caplog: LogCaptureFixture):
    json_caplog.set_level("WARNING")
    r = Success(42, warnings=["careful"])
    assert unwrap(r, throw=False) == 42
    assert '"warnings": ["careful"]}' in json_caplog.text


def test_unwrap_failure_no_throw(json_caplog: LogCaptureFixture):
    json_caplog.set_level("ERROR")
    r = Failure(reason="x", error="broken")
    assert unwrap(r, throw=False) is None
    assert '"reason": "x", "error": "broken"' in json_caplog.text


def test_unwrap_failure_with_throw():
    f1 = Failure(reason="x", error="boom")
    with pytest.raises(AppError) as exc:
        unwrap(f1, throw=True)
    assert "x: boom" in str(exc)
    f2 = Failure(reason="x")
    with pytest.raises(AppError) as exc:
        unwrap(f2, throw=True)
    assert exc.value.args[0] == "x"


def test_prepare_loads_state_and_reconciles_backend(
    backend: Mock, orchestrator: Orchestrator, registry: Mock, state: Mock
):
    asset = Mock(name="asset")
    stored_asset = Mock(name="stored_asset")
    series = Mock(name="series")
    stored_series = Mock(name="stored_series")

    state.load.return_value = Success(3)
    backend.get_assets.return_value = Success([asset])
    registry.merge_and_find_new_assets.return_value = [asset]
    backend.store_asset.return_value = Success(stored_asset)

    backend.get_series.return_value = Success([series])

    reconciled = Mock()
    reconciled.to_persist = [series]
    registry.reconcile_series.return_value = reconciled
    backend.store_series.return_value = Success(stored_series)

    orchestrator._prepare()

    state.load.assert_called_once_with()
    backend.get_assets.assert_called_once_with()
    registry.merge_and_find_new_assets.assert_called_once_with([asset])

    backend.store_asset.assert_called_once_with(asset)
    registry.register_stored_asset.assert_called_once_with(stored_asset)

    backend.get_series.assert_called_once_with(registry.get_asset_by_id)
    registry.reconcile_series.assert_called_once_with([series])

    backend.store_series.assert_called_once_with(series)
    registry.register_stored_series.assert_called_once_with(stored_series)

    backend.refresh_short_lived_series_ids.assert_called_once_with()


def test_prepare_does_not_persist_when_nothing_changed(
    backend: Mock, orchestrator: Orchestrator, registry: Mock, state: Mock
):
    state.load.return_value = Success(0)
    backend.get_assets.return_value = Success([])
    registry.merge_and_find_new_assets.return_value = []

    backend.get_series.return_value = Success([])

    reconciled = Mock()
    reconciled.to_persist = []
    registry.reconcile_series.return_value = reconciled

    orchestrator._prepare()

    backend.store_asset.assert_not_called()
    backend.store_series.assert_not_called()
    registry.register_stored_asset.assert_not_called()
    registry.register_stored_series.assert_not_called()
    backend.refresh_short_lived_series_ids.assert_called_once_with()


def test_prepare_continues_when_wal_load_fails(backend: Mock, orchestrator: Orchestrator, registry: Mock, state: Mock):
    state.load.return_value = Failure(reason="WAL error")

    backend.get_assets.return_value = Success([])
    registry.merge_and_find_new_assets.return_value = []
    backend.get_series.return_value = Success([])

    reconciled = Mock()
    reconciled.to_persist = []
    registry.reconcile_series.return_value = reconciled

    orchestrator._prepare()

    backend.get_assets.assert_called_once_with()


def test_ingest_points_ingests_all_points_and_updates_range(
    orchestrator: Orchestrator, series: Mock, state: Mock, ts: Creator[datetime]
):

    first = SeriesPoint(series.id, time=ts(0), close=0.0)
    second = SeriesPoint(series.id, time=ts(1), close=0.1)

    state.ingest.return_value = Success(None)

    stored_range = SeriesState(first_point=first.time, last_point=second.time)
    state.series_state[series.id] = stored_range

    # first test: order low-high
    result = orchestrator._ingest_points([first, second], series)

    assert result is True, "low-high ok"
    assert state.ingest.call_args_list == [((first,), {}), ((second,), {})]
    state.update_state.assert_called_once_with(42, first.time, second.time)

    # second test: order high-low
    state.update_state.reset_mock()

    result = orchestrator._ingest_points([second, first], series)

    assert result is True, "high-low ok"
    state.update_state.assert_called_once_with(42, first.time, second.time)


def test_ingest_points_does_not_update_range_when_point_ingestion_fails(
    orchestrator: Orchestrator, series: Mock, state: Mock
):
    points = []

    for hour in (10, 11, 12):
        point = SeriesPoint(series.id, time=datetime(2026, 8, 20, hour, tzinfo=UTC), close=0)
        points.append(point)

    state.ingest.side_effect = [
        Success(None),
        Failure(reason="database error"),
        Success(None),
    ]

    all_ok = orchestrator._ingest_points(points, series)

    assert not all_ok
    assert state.ingest.call_count == 3
    state.update_state.assert_not_called()


def test_handle_fetch_response_failed_fetch(backend: Mock, orchestrator: Orchestrator, registry: Mock):
    result = Failure(reason="fetch failed", error="connection error")

    assert orchestrator._handle_fetch_response(result) is False

    registry.get_series_by_id.assert_not_called()
    backend.store_asset.assert_not_called()


def test_handle_fetch_response_ingests_points_no_metadata(orchestrator: Orchestrator, registry: Mock, series: Mock):
    point = SeriesPoint(series_id=series.id, time=datetime(2026, 8, 20, 10, tzinfo=UTC), close=0.0)
    result = Success(FetchData(series_id=series.id, series=series, metadata=None, points=[point]))
    registry.get_series_by_id.return_value = series
    orchestrator._ingest_points = Mock(return_value=True)

    assert orchestrator._handle_fetch_response(result) is True

    orchestrator._ingest_points.assert_called_once_with([point], series)
    registry.register_provider_metadata.assert_not_called()


def test_handle_fetch_response_registers_provider_metadata_without_persisting(
    backend: Mock, orchestrator: Orchestrator, registry: Mock, series: Mock
):
    metadata = AssetMetadata(short_name="abc")

    result = Success(payload=FetchData(series_id=1, series=series, points=[], metadata=metadata))

    registry.get_series_by_id.return_value = series
    registry.register_provider_metadata.return_value = None
    assert orchestrator._handle_fetch_response(result) is True

    registry.register_provider_metadata.assert_called_once_with(series.asset, metadata)
    backend.store_asset.assert_not_called()


def test_handle_fetch_response_persists_changed_asset_metadata(
    backend: Mock, orchestrator: Orchestrator, registry: Mock, asset, series: Mock
):
    metadata = AssetMetadata(short_name="abc")
    stored_asset = Mock()

    result = Success(FetchData(series_id=series.id, series=series, metadata=metadata, points=[]))
    registry.register_provider_metadata.return_value = asset
    backend.store_asset.return_value = Success(stored_asset)

    assert orchestrator._handle_fetch_response(result) is True

    registry.register_provider_metadata.assert_called_once_with(asset, metadata)
    backend.store_asset.assert_called_once_with(asset)

    # This should be register_stored_asset(), not register_stored_series().
    registry.register_stored_asset.assert_called_once_with(stored_asset)


def test_handle_fetch_response_processes_metadata_and_points(orchestrator: Orchestrator, registry: Mock, series: Mock):
    metadata = AssetMetadata(short_name="abc")
    point = Mock()
    result = Success(FetchData(series_id=series.id, series=series, metadata=metadata, points=[point]))

    registry.register_provider_metadata.return_value = None

    orchestrator._ingest_points = Mock(return_value=True)

    assert orchestrator._handle_fetch_response(result) is True
    registry.register_provider_metadata.assert_called_once_with(series.asset, metadata)
    orchestrator._ingest_points.assert_called_once_with([point], series)


def test_handle_fetch_response_no_points_does_not_ingest(orchestrator: Orchestrator, registry: Mock, series: Mock):

    result = Success(FetchData(series_id=series.id, series=series, metadata=None, points=[]))
    registry.get_series_by_id.return_value = series

    orchestrator._ingest_points = Mock()
    assert orchestrator._handle_fetch_response(result) is True
    orchestrator._ingest_points.assert_not_called()


def test_finalize_saves_state_and_returns_zero_on_success(orchestrator: Orchestrator, state: Mock):
    assert orchestrator._finalize(0) == 0
    state.save.assert_called_once_with()


def test_finalize_saves_state_and_returns_one_when_fetches_failed(orchestrator: Orchestrator, state: Mock):
    assert orchestrator._finalize(3) == 1
    state.save.assert_called_once_with()


def test_run_prepares_processes_fetches_and_finalizes(fetcher: Mock, registry: Mock, orchestrator: Orchestrator):
    orchestrator._prepare = Mock()
    orchestrator._handle_fetch_response = Mock(return_value=True)
    orchestrator._finalize = Mock(return_value=0)

    result1 = Mock()
    result2 = Mock()
    series1 = Mock()

    registry.all_series.return_value = series1

    fetcher.fetch_incrementally.return_value = [result1, result2]

    assert orchestrator.run() == 0

    orchestrator._prepare.assert_called_once_with()
    fetcher.fetch_incrementally.assert_called_once_with(series1, orchestrator.state)

    assert orchestrator._handle_fetch_response.call_args_list == [
        ((result1,), {}),
        ((result2,), {}),
    ]

    orchestrator._finalize.assert_called_once_with(0)


def test_run_counts_failed_fetch_responses(fetcher: Mock, orchestrator: Orchestrator):
    orchestrator._prepare = Mock()
    orchestrator._handle_fetch_response = Mock(side_effect=[True, False, False, True])
    orchestrator._finalize = Mock(return_value=1)

    results = [Mock(), Mock(), Mock(), Mock()]
    fetcher.fetch_incrementally.return_value = results

    assert orchestrator.run() == 1

    orchestrator._prepare.assert_called_once_with()
    orchestrator._handle_fetch_response.assert_has_calls([call(result) for result in results])
    orchestrator._finalize.assert_called_once_with(2)


def test_run_finalizes_successfully_when_nothing_is_fetched(fetcher: Mock, orchestrator: Orchestrator):
    orchestrator._prepare = Mock()
    orchestrator._handle_fetch_response = Mock()
    orchestrator._finalize = Mock(return_value=0)

    fetcher.fetch_incrementally.return_value = []

    assert orchestrator.run() == 0

    orchestrator._handle_fetch_response.assert_not_called()
    orchestrator._finalize.assert_called_once_with(0)
