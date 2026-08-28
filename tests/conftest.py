# Copyright 2026 Rik Essenius
# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.
# File: tests/conftest.py

import logging
from collections.abc import Callable, Iterator
from datetime import datetime, time
from pathlib import Path
from unittest.mock import Mock

import pytest
from pytest import LogCaptureFixture

from finance.common.applogger import JsonFormatter, LogConfig, LogConfigurator
from finance.common.model import Asset, AssetMetadata, Series
from finance.common.string_enums import Retention, SeriesType
from finance.common.time_utils import UTC
from finance.common.types import Failure, Result, Unwrap
from finance.state.state import State
from tests.support.types import AssertError, Creator, Factory, StateContext

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
def unwrap[T]() -> Unwrap[T]:

    def _unwrap(result: Result[T]) -> T:
        assert result.ok is True, "result is Success"
        assert result.payload is not None, "Payload set"
        return result.payload

    return _unwrap


# in case we need two different unwraps in one tests
@pytest.fixture
def unwrap2(unwrap: Unwrap) -> Unwrap:
    return unwrap


@pytest.fixture
def assert_error() -> AssertError:
    def _assert_error(result: Result, reason: str, error: str | None = None) -> None:
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
        assert result.ok is True
        if warning is None:
            assert result.warnings is None
        else:
            assert any(warning in w for w in result.warnings), f"warning '{warning}' not found"

    return _assert_warning


# ---------------------------------------------------------------------------
# Domain object factories
# ---------------------------------------------------------------------------


@pytest.fixture
def make_metadata() -> Creator[AssetMetadata]:
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
def make_asset(make_metadata: Creator[AssetMetadata]) -> Creator[Asset]:
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
def make_series(make_asset: Creator[Asset]) -> Creator[Series]:
    def _make(asset: Asset, **overrides) -> Series:

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
def state_deps() -> tuple[Mock, Mock]:
    wal = Mock()
    backend = Mock()

    wal.peek.return_value = None
    wal.read_all.return_value = []
    wal.dequeue_multiple.side_effect = lambda n: n
    wal.enqueue.return_value = None

    return backend, wal


@pytest.fixture
def state_env(state_deps: tuple[Mock, Mock]) -> StateContext:
    """Provides a State with mocked WAL and mocked backend."""

    backend, wal = state_deps
    state = State(backend, wal)
    return state, backend, wal


@pytest.fixture
def state(state_env: StateContext) -> State:
    return state_env[0]


@pytest.fixture()
def ts() -> Creator[datetime]:
    def _make(ts1: int) -> datetime:
        return datetime.fromtimestamp(ts1, tz=UTC)

    return _make


# ---------------------------------------------------------------------------
# Logging fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def setup_logging() -> Iterator[None]:
    cfg = LogConfig.from_config({"level": "debug"})

    log_config = LogConfigurator()
    log_config.bootstrap()
    log_config.setup(cfg)
    yield


@pytest.fixture
def json_caplog(caplog: LogCaptureFixture, setup_logging: Iterator[None]) -> LogCaptureFixture:
    # setup_logging is intentionally unused: its side effect configures logging.

    caplog.handler.setFormatter(JsonFormatter())
    return caplog


@pytest.fixture
def clean_logging() -> Iterator[None]:
    root = logging.getLogger()

    # Remove all handlers
    for h in list(root.handlers):
        root.removeHandler(h)

    root.handlers.clear()
    root.setLevel(logging.NOTSET)

    # After test, restore pytest logging
    yield
