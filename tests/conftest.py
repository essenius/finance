# Copyright 2026 Rik Essenius
# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.
# File: tests/conftest.py

from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import Mock

import pytest

from finance.common.model import INTRADAY, Asset, Result, Series, SeriesType
from finance.common.time_utils import parse_duration
from finance.state.state import State
from finance.state.storage import StateStorage
from finance.state.wal import JsonlWAL
from finance.timeseries.timescale_backend import TimescaleBackend


class MockStorage:
    def __init__(self, path: Path):
        self.path = path

    def load(self):
        return {}

    def save(self, data):
        pass


@pytest.fixture
def state_deps(tmp_path):
    wal = Mock()
    backend = Mock()
    storage = StateStorage(tmp_path / "state.json")

    wal.peek.return_value = None
    wal.read_all.return_value = []
    wal.dequeue.return_value = None
    wal.enqueue.return_value = None

    return backend, wal, storage


@pytest.fixture
def state_env(state_deps) -> tuple[State, TimescaleBackend, JsonlWAL, StateStorage]:
    """Provides a State with mocked WAL + TS client + resolved path."""

    backend, wal, storage = state_deps
    state = State(backend, wal, storage)
    state._rebuild_measurement_state = lambda series_id: None

    return state, backend, wal, storage


@pytest.fixture
def fixed_now():
    return lambda: datetime(2025, 6, 15, 15, 6, 40, tzinfo=UTC)
    # equals timestamp 1_750_000_000


@pytest.fixture
def state(state_env) -> State:
    state, _, _, _ = state_env
    return state


@pytest.fixture
def unwrap():

    def _unwrap(result: Result):
        assert result.ok
        assert result.payload is not None
        return result.payload

    return _unwrap


@pytest.fixture
def assert_error():
    def _assert_error(result: Result, reason: str, error: str | None):
        assert not result.ok, "ok is true"
        assert result.payload is None, f"Payload is not None but {result.payload}"
        assert reason in result.reason, f"Reason '{result.reason}' is not correct"
        if result.error:
            assert error in result.error, f"Error '{result.error}' is not correct"
        else:
            assert result.error is None, f"Error is not None but {result.error}"

    return _assert_error


@pytest.fixture
def assert_warning():
    def _assert_warning(result: Result, warning: str):
        assert result.ok
        if warning is None:
            assert result.warnings is None
        else:
            assert any(warning in w for w in result.warnings)
        assert result.reason is None
        return result.payload

    return _assert_warning


@pytest.fixture
def make_asset():
    def _make(name: str = "eur_usd", **overrides) -> Asset:
        defaults = {
            "id": 1,
            "name": name,
            "symbol": name,
            "provider": "yahoo",
            "provider_code": "EURUSD=X",
            "display_name": f"d_{name}",
            "instrument": "forex",
            "region": "Europe",
            "exchange": "DEX",
            "currency": "USD",
            "unit": "EUR",
        }
        return Asset(**(defaults | overrides))

    return _make


@pytest.fixture
def make_series(make_asset):
    def _make(
        asset: Asset | None, **overrides
    ):  # interval="10m", history_limit="5d", resolution=INTRADAY, series_type=SeriesType.VALUE, id=1):
        if asset is None:
            asset = make_asset()

        defaults = {
            "id": asset.id,
            "resolution": INTRADAY,
            "asset_id": asset.id,
            "symbol": asset.name,
            "series_type": SeriesType.VALUE,
            "interval": "10m",
            "history_limit": "5d",
        }
        params = defaults | overrides
        params["name"] = f"{asset.name}_{params['resolution']}"
        params["interval_seconds"] = parse_duration(params["interval"])
        params["history_limit_seconds"] = parse_duration(params["history_limit"])

        return Series(**params)

    return _make
