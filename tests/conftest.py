# Copyright 2026 Rik Essenius
# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.
# File: tests/conftest.py

from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import Mock

import pytest

from finance.common.model import Result
from finance.state.state import JsonlWAL, State
from finance.state.storage import StateStorage
from finance.timeseries.influx import InfluxBackend


def bucket_for_test(measurement: str) -> str:
    return "test_bucket"


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
    influx = Mock()
    storage = StateStorage(tmp_path / "state.json")

    wal.peek.return_value = None
    wal.read_all.return_value = []
    wal.dequeue.return_value = None
    wal.enqueue.return_value = None

    return influx, wal, storage


@pytest.fixture
def state_env(state_deps) -> tuple[State, InfluxBackend, JsonlWAL, StateStorage]:
    """Provides a State with mocked WAL + TS client + resolved path."""

    influx, wal, storage = state_deps
    state = State(influx, wal, storage, bucket_for_test)
    state._rebuild_measurement_state = lambda measurement: None

    return state, influx, wal, storage


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
