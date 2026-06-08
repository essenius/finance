import pytest

from finance.common.model import TimeseriesWrite
from finance.state.manager import State

# state_env is defined in the parent folder's conftest.py


@pytest.fixture
def state(state_env) -> State:
    state, ts, wal, path = state_env
    return state


@pytest.fixture
def make_entry() -> TimeseriesWrite:
    def _make(measurement="spx", value=1, timestamp=100, bucket="bucket"):
        return TimeseriesWrite(
            measurement=measurement,
            fields={"v": value},
            timestamp=timestamp,
            bucket=bucket,
            tags={},
        )
    return _make


@pytest.fixture
def mock_rebuild(monkeypatch):
    def apply(result):
        monkeypatch.setattr(
            "finance.state.manager.rebuild_measurement_state",
            lambda bucket, measurement, wal, ts_client: result
        )
    return apply


@pytest.fixture
def wal_sequence():
    return lambda wal, seq: setattr(wal.peek, "side_effect", seq)


@pytest.fixture
def two_wal_entries(make_entry):
    def _entries():
        return [
            make_entry(measurement="a", value=1, timestamp=10),
            make_entry(measurement="a", value=2, timestamp=20),
        ]
    return _entries

@pytest.fixture
def two_wal_entries_with_none(make_entry):
    def _entries():
        return [
            make_entry(measurement="a", value=1, timestamp=10),
            make_entry(measurement="a", value=2, timestamp=20),
            None,
        ]
    return _entries
