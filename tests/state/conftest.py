from unittest.mock import Mock

import pytest

from finance.state.manager import State


@pytest.fixture
def state_env(tmp_path):
    """Provides a State with mocked WAL + TS client + resolved path."""

    wal = Mock()
    ts = Mock()
    wal.peek.return_value = None

    path = tmp_path / "state.json"

    state = State(ts, wal, path)
    return state, ts, wal, path


@pytest.fixture
def make_entry():
    return lambda m="spx", v=1, ts=100, b="bucket": {
        "bucket": b,
        "measurement": m,
        "fields": {"v": v},
        "timestamp": ts,
    }

@pytest.fixture
def mock_rebuild(monkeypatch):
    return lambda result: monkeypatch.setattr(
        "finance.state.manager.rebuild_measurement_state",
        lambda m, w, t: result
    )

@pytest.fixture
def wal_sequence():
    return lambda wal, seq: setattr(wal.peek, "side_effect", seq)

@pytest.fixture
def two_wal_entries(make_entry):
    return lambda me=make_entry: [
        me("a", 1, 10, "b"),
        me("a", 2, 20, "b"),
    ]
@pytest.fixture
def two_wal_entries_with_none(two_wal_entries):
    return lambda: two_wal_entries() + [None]
