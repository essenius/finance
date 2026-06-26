# Copyright 2026 Rik Essenius
# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.
# File: tests/state/test_state.py

import json
from unittest.mock import Mock

from finance.common.model import SeriesState
from finance.state.state import State
from finance.state.storage import StateStorage

# ---------------------------------------------------------------------------
# get() tests
# ---------------------------------------------------------------------------


def test_get_returns_cached_entry(state_env):
    """If measurement exists in state, return it without rebuild."""

    state, backend, wal, _ = state_env
    my_state = SeriesState(first_timestamp=10, last_timestamp=10)
    state.series = {1: my_state}
    result = state.get(1)
    assert result == my_state
    wal.read_all.assert_not_called()
    backend.read_first.assert_not_called()


def test_get_triggers_rebuild_when_missing(state):
    """If measurement missing, State should rebuild measurement state."""

    state._rebuild_measurement_state = lambda m: SeriesState(first_timestamp=123, last_timestamp=123)
    state._state = {}
    result = state.get(1)
    assert result == SeriesState(first_timestamp=123, last_timestamp=123)
    assert state.series[1] == result


def test_get_returns_none_when_rebuild_finds_nothing(state):
    state._rebuild_measurement_state = state._rebuild_measurement_state = lambda m: None
    state.series = {}
    assert state.get(1) is None
    assert 1 not in state.series


# ---------------------------------------------------------------------------
# save() tests
# ---------------------------------------------------------------------------


def test_save_writes_actual_file(tmp_path):
    path = tmp_path / "state.json"
    storage = StateStorage(path)
    wal = Mock()
    ts = Mock()
    state = State(ts, wal, storage)
    state.series = {1: SeriesState(last_timestamp=50)}

    state.save()

    assert path.exists()
    assert json.loads(path.read_text()) == {"1": {"first_timestamp": None, "last_timestamp": 50, "last_try": None}}


def test_save_does_not_mutate_state():

    state = State(backend=Mock(), wal=Mock(), storage=Mock())
    state.series = {2: SeriesState(last_timestamp=10)}

    before = dict(state.series)

    state.save()

    assert state.series == before


# -------------------
# update after fetch
# -------------------


def test_update_after_fetch_no_new_data(state):
    state.series[1] = SeriesState(last_timestamp=200)
    state.update_after_fetch(1, 1000)
    assert state.series[1].last_try == 1000


def test_update_when_not_captured(state):
    state.update_after_fetch(2, 777)
    assert state.series[2].last_try == 777


def test_iter_metrics(state):

    state.series = {
        1: SeriesState(first_timestamp=0, last_timestamp=10),
        2: SeriesState(first_timestamp=10, last_timestamp=20),
    }

    items = list(state.iter_series_state())

    assert (1, SeriesState(first_timestamp=0, last_timestamp=10)) in items
    assert (2, SeriesState(first_timestamp=10, last_timestamp=20)) in items


# --------------------------
# rebuild measurement state
# --------------------------


def test_get_last_timestamp_triggers_rebuild(state):
    state._rebuild_measurement_state = lambda m: SeriesState(first_timestamp=123, last_timestamp=123)
    state.series = {}

    assert state.get_last_timestamp(1) == 123
    assert state.series[1].last_timestamp == 123


def test_get_last_timestamp_returns_none_when_missing(state):
    state._rebuild_measurement_state = lambda m: None
    state._state = {}

    assert state.get_last_timestamp(2) is None
    assert 2 not in state.series


# --------------------------
# update composite removed from V1 scope
# --------------------------
"""
def test_update_composite(state):
    state.update_composite("comp", {"v": 42}, 999)

    assert state.series["comp"] == {
        "fields": {"v": 42},
        "last_timestamp": 999,
    }
"""
# -------------
# Update range
# -------------


def test_update_range_initializes_missing_timestamps(state):
    state.series = {1: SeriesState()}
    state.update_range(1, first=100, last=200)
    assert state.series[1] == SeriesState(first_timestamp=100, last_timestamp=200)


def test_update_range_expands_forward(state):
    state.series = {1: SeriesState(first_timestamp=100, last_timestamp=200)}
    state.update_range(1, first=150, last=300)
    assert state.series[1] == SeriesState(first_timestamp=100, last_timestamp=300)


def test_update_range_expands_backward(state):
    state.series = {1: SeriesState(first_timestamp=100, last_timestamp=200)}
    state.update_range(1, first=50, last=150)
    assert state.series[1] == SeriesState(first_timestamp=50, last_timestamp=200)


def test_update_range_does_not_shrink(state):
    state.series = {1: SeriesState(first_timestamp=100, last_timestamp=200)}
    state.update_range(1, first=120, last=180)
    assert state.series[1] == SeriesState(first_timestamp=100, last_timestamp=200)
