from pathlib import Path
from unittest.mock import Mock

import pytest

from finance.common.model import Result
from finance.state.manager import JsonlWAL, State
from finance.timeseries.influx import InfluxBackend


def bucket_for_test(measurement: str) -> str:
    return "test_bucket"

@pytest.fixture
def state_env(tmp_path) -> tuple[State, InfluxBackend, JsonlWAL, Path]:
    """Provides a State with mocked WAL + TS client + resolved path."""

    wal = Mock()
    influx = Mock()
    wal.peek.return_value = None
    wal.read_all.return_value = []
    wal.dequeue.return_value = None
    wal.enqueue.return_value = None
    path = tmp_path / "state.json"

    state = State(influx, wal, path, bucket_for_test)
    return state, influx, wal, path


@pytest.fixture
def unwrap():

    def _unwrap(result: Result):
        assert result.ok
        assert result.payload is not None
        return result.payload
    return _unwrap


@pytest.fixture
def assert_error():
    def _assert_error(result: Result, reason: str, error: str|None):
        assert not result.ok
        assert result.payload is None
        assert reason in result.reason
        if result.error:
            assert error in result.error
        else:
            assert result.error is None
    return _assert_error
