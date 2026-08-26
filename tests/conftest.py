# Copyright 2026 Rik Essenius
# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.
# File: tests/conftest.py

import logging
from collections.abc import Callable
from datetime import datetime, time
from pathlib import Path
from unittest.mock import Mock

import pytest

from finance.common.applogger import JsonFormatter, LogConfig, LogConfigurator
from finance.common.model import Asset, AssetMetadata, Series
from finance.common.string_enums import Retention, SeriesType
from finance.common.time_utils import UTC
from finance.common.types import Failure, Result
from finance.state.state import State
from finance.state.wal import JsonlWAL
from finance.timeseries.series_backend import SeriesBackend
from tests.support.types import ConfigurableFactory, Factory

# ---------------------------------------------------------------------------
# Test doubles
# ---------------------------------------------------------------------------


class MockStorage:
    def __init__(self, path: Path):
        self.path = path

    def load(self):
        return {}

    def save(self, data):
        pass


# ---------------------------------------------------------------------------
# Common test values
# ---------------------------------------------------------------------------


@pytest.fixture
def fixed_now() -> Factory[datetime]:
    return lambda: datetime(2025, 6, 15, 15, 6, 40, tzinfo=UTC)


# ---------------------------------------------------------------------------
# Result helpers
# ---------------------------------------------------------------------------


@pytest.fixture
def unwrap() -> Callable[[Result], object]:

    def _unwrap(result: Result) -> object:
        assert result.ok is True, "result is Success"
        assert result.payload is not None, "Payload set"
        return result.payload

    return _unwrap


@pytest.fixture
def assert_error() -> Callable[[Result, str, str | None], None]:
    def _assert_error(result: Result, reason: str, error: str | None) -> None:
        assert result.ok is False, "ok is false"
        assert isinstance(result, Failure), "result is a Failure"
        assert reason in result.reason, f"Reason '{result.reason}' != expected '{reason}"
        if result.error is not None:
            assert error is not None
            assert error in str(result.error), f"Error '{result.error}' != expected '{error}'"
        else:
            assert result.error is None, f"Error is not None but {result.error}"

    return _assert_error


@pytest.fixture
def assert_warning() -> Callable[[Result, str | None], object]:
    def _assert_warning(result: Result, warning: str | None) -> None:
        assert result.ok
        if warning is None:
            assert result.warnings is None
        else:
            assert any(warning in w for w in result.warnings), f"warning '{warning}' not found"

    return _assert_warning


# ---------------------------------------------------------------------------
# Domain object factories
# ---------------------------------------------------------------------------


@pytest.fixture
def make_metadata() -> Factory[AssetMetadata]:
    # CO: "long_name": f"d_{name}",

    def _make(**overrides) -> AssetMetadata:
        defaults = {
            "long_name": None,
            "short_name": None,
            "instrument": "forex",
            "region": "Europe",
            "exchange": "DEX",
            "currency": "USD",
            "unit": "EUR",
            "timezone": UTC,
            "first_trade_date": None,
            "market_open": time.min,
            "market_close": time.max,
            "week_start": "mon",
            "week_end": "fri",
        }
        return AssetMetadata(**(defaults | overrides))

    return _make


@pytest.fixture
def make_asset(make_metadata) -> Factory[Asset]:
    def _make(name: str = "eur_usd", **overrides) -> Asset:
        defaults = {
            "id": 1,
            "name": name,
            "symbol": name,
            "provider": "yahoo",
            "provider_code": "EURUSD=X",
        }
        meta = overrides.get("config_metadata")
        if meta is None:
            meta = make_metadata()
            defaults["config_metadata"] = meta
        if overrides.get("effective_metadata") is None:
            defaults["effective_metadata"] = meta
        return Asset(**(defaults | overrides))

    return _make


@pytest.fixture
def make_series(make_asset) -> ConfigurableFactory[Series]:
    def _make(asset: Asset | None, **overrides) -> Series:
        if asset is None:
            asset = make_asset()
            assert asset is not None

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
            "publication_offset": None,
        }
        params = defaults | overrides
        params["name"] = f"{asset.name}:{params['code']}"

        return Series(**params)

    return _make


# ---------------------------------------------------------------------------
# State fixtures
# ---------------------------------------------------------------------------


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
def state(state_env) -> State:
    state, _, _ = state_env
    return state


@pytest.fixture()
def ts() -> ConfigurableFactory[datetime]:
    def _make(ts1: int) -> datetime:
        return datetime.fromtimestamp(ts1, tz=UTC)

    return _make


# ---------------------------------------------------------------------------
# Logging fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def setup_logging():
    cfg = LogConfig.from_config({"level": "debug"})

    log_config = LogConfigurator()
    log_config.bootstrap()
    log_config.setup(cfg)
    yield


@pytest.fixture
def json_caplog(caplog, setup_logging):
    # setup_logging is intentionally unused: its side effect configures logging.

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
