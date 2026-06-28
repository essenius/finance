# Copyright 2026 Rik Essenius
# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.
# File: tests/state/test_state.py

from datetime import datetime, timedelta
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
    my_state = SeriesState(first_time=10, last_time=10)
    state.series = {1: my_state}
    result = state.get(1)
    assert result == my_state
    wal.read_all.assert_not_called()
    backend.read_first.assert_not_called()


def test_get_triggers_rebuild_when_missing(state):
    """If measurement missing, State should rebuild measurement state."""

    state._rebuild_measurement_state = lambda m: SeriesState(first_time=123, last_time=123)
    state._state = {}
    result = state.get(1)
    assert result == SeriesState(first_time=123, last_time=123)
    assert state.series[1] == result


def test_get_returns_none_when_rebuild_finds_nothing(state):
    state._rebuild_measurement_state = state._rebuild_measurement_state = lambda m: None
    state.series = {}
    assert state.get(1) is None
    assert 1 not in state.series


# ---------------------------------------------------------------------------
# save() tests
# ---------------------------------------------------------------------------


def test_save_writes_actual_file(tmp_path, fixed_now):
    now = fixed_now()
    path = tmp_path / "state.json"
    storage = StateStorage(path)
    wal = Mock()
    ts = Mock()
    state = State(ts, wal, storage)
    state.series = {1: SeriesState(last_time=now)}

    state.save()

    assert path.exists()
    assert json.loads(path.read_text()) == {"1": {"first_time": None, "last_time": now.isoformat(timespec="seconds"), "last_try": None}}


def test_save_does_not_mutate_state():

    state = State(backend=Mock(), wal=Mock(), storage=Mock())
    state.series = {2: SeriesState(last_time=10)}

    before = dict(state.series)

    state.save()

    assert state.series == before


# -------------------
# update after fetch
# -------------------


def test_update_after_fetch_no_new_data(state, fixed_now):

    state.series[1] = SeriesState(last_time=datetime.min)
    now = fixed_now()
    state.update_after_fetch(1, now)
    assert state.series[1].last_try == now


def test_update_when_not_captured(state):
    state.update_after_fetch(2, datetime.min)
    assert state.series[2].last_try == datetime.min


def test_iter_metrics(state, fixed_now):

    first = datetime.min
    between = fixed_now()
    last = datetime.max
    state.series = {
        1: SeriesState(first_time=first, last_time=between),
        2: SeriesState(first_time=between, last_time=last),
    }

    items = list(state.iter_series_state())

    assert (1, SeriesState(first_time=first, last_time=between)) in items
    assert (2, SeriesState(first_time=between, last_time=last)) in items


# --------------------------
# rebuild measurement state
# --------------------------


def test_get_last_time_triggers_rebuild(state, fixed_now):
    now = fixed_now()
    state._rebuild_measurement_state = lambda m: SeriesState(first_time=now, last_time=now)
    state.series = {}

    assert state.get_last_time(1) == now
    assert state.series[1].last_time == now


def test_get_last_timestamp_returns_none_when_missing(state):
    state._rebuild_measurement_state = lambda m: None
    state._state = {}

    assert state.get_last_time(2) is None
    assert 2 not in state.series


# ---------------------------------------
# update composite removed from V1 scope
# ---------------------------------------
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
    state.update_range(1, first=datetime.min, last=datetime.max)
    assert state.series[1] == SeriesState(first_time=datetime.min, last_time=datetime.max)


def test_update_range_expands_forward(state):
    first = datetime.min
    current = first + timedelta(seconds=200)
    range_min = current - timedelta(seconds=50)
    range_max = current + timedelta(seconds=100)
    state.series = {1: SeriesState(first_time=first, last_time=current)}
    state.update_range(1, first=range_min, last=range_max)
    assert state.series[1] == SeriesState(first_time=first, last_time=range_max)


def test_update_range_expands_backward(state):
    range_min = datetime.min
    first = range_min + timedelta(seconds=50)
    current = first + timedelta(seconds=200)
    state.series = {1: SeriesState(first_time=first, last_time=current)}
    state.update_range(1, first=range_min, last=current)
    assert state.series[1] == SeriesState(first_time=range_min, last_time=current)


def test_update_range_does_not_shrink(state):
    first = datetime.min
    current = first + timedelta(seconds=100)
    range_min = first + timedelta(seconds=20)
    range_max = current - timedelta(seconds=20)
    state.series = {1: SeriesState(first_time=first, last_time=current)}
    state.update_range(1, first=range_min, last=range_max)
    assert state.series[1] == SeriesState(first_time=first, last_time=current)
