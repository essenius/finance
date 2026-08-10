# Copyright 2026 Rik Essenius
# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.
# File: tests/conftest.py

import logging
from datetime import UTC, datetime, time
from pathlib import Path
from unittest.mock import Mock

import pytest

from finance.common.applogger import JsonFormatter, LogConfig
from finance.common.model import Asset, Series
from finance.common.result import Result
from finance.common.string_enums import Retention, SeriesType
from finance.state.state import State
from finance.state.wal import JsonlWAL
from finance.timeseries.series_backend import SeriesBackend


class MockStorage:
    def __init__(self, path: Path):
        self.path = path

    def load(self):
        return {}

    def save(self, data):
        pass


@pytest.fixture
def state_deps():
    wal = Mock()
    backend = Mock()

    wal.peek.return_value = None
    wal.read_all.return_value = []
    wal.dequeue_multiple.side_effect = lambda n: n
    wal.enqueue.return_value = None

    return backend, wal


@pytest.fixture
def state_env(state_deps) -> tuple[State, SeriesBackend, JsonlWAL]:
    """Provides a State with mocked WAL + TS client + resolved path."""

    backend, wal = state_deps
    state = State(backend, wal)
    return state, backend, wal


@pytest.fixture
def fixed_now():
    return lambda: datetime(2025, 6, 15, 15, 6, 40, tzinfo=UTC)


@pytest.fixture
def state(state_env) -> State:
    state, _, _ = state_env
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
            assert any(warning in w for w in result.warnings), f"warning '{warning}' not found"
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
    def _make(asset: Asset | None, **overrides):
        if asset is None:
            asset = make_asset()

        defaults = {
            "id": asset.id,
            "code": "dummy",
            "asset_id": asset.id,
            "asset_name": asset.name,
            "interval": "10m",
            "series_type": SeriesType.VALUE,
            "retention": Retention.SHORT_LIVED,
            "retention_period": "30d",
            "bootstrap_history": "5d",
            "timezone": UTC,
            "publication_offset": None,
            "market_open": time.min,
            "market_close": time.max,
            "week_start": "mon",
            "week_end": "fri",
        }
        params = defaults | overrides
        params["name"] = f"{asset.name}:{params['code']}"

        return Series(**params)

    return _make


@pytest.fixture
def setup_logging():
    cfg = {
        "level": "debug",
        "json": True,
    }

    log_config = LogConfig()
    log_config.bootstrap()
    log_config.setup(cfg)
    yield


@pytest.fixture
def json_caplog(caplog, setup_logging):
    caplog.handler.setFormatter(JsonFormatter())
    return caplog


@pytest.fixture
def clean_logging():
    root = logging.getLogger()

    # Remove all handlers
    for h in list(root.handlers):
        root.removeHandler(h)

    root.handlers.clear()
    root.setLevel(logging.NOTSET)

    # After test, restore pytest logging
    yield
