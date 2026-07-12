# Copyright 2026 Rik Essenius
# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.
# File: tests/state/test_state.py

import json
from datetime import datetime, timedelta
from unittest.mock import Mock

from finance.common.model import Result, SeriesState
from finance.state.state import State
from finance.state.storage import StateStorage

# ---------------------------------------------------------------------------
# get() tests
# ---------------------------------------------------------------------------


def test_get_returns_cached_entry(state_env):
    """If measurement exists in state, return it without rebuild."""

    state, backend, wal, _ = state_env
    my_state = SeriesState(first_point=10, last_point=10)
    state.series = {1: my_state}
    result = state.get_series_state(1)
    assert result == my_state
    wal.read_all.assert_not_called()
    backend.read_first.assert_not_called()


def test_get_triggers_rebuild_when_missing(state):
    """If measurement missing, State should rebuild measurement state."""

    state._rebuild_measurement_state = lambda m: SeriesState(first_point=123, last_point=123)
    state._state = {}
    result = state.get_series_state(1)
    assert result == SeriesState(first_point=123, last_point=123)
    assert state.series[1] == result


def test_get_returns_none_when_rebuild_finds_empty(state):
    state._rebuild_measurement_state = state._rebuild_measurement_state = lambda m: SeriesState()
    state.series = {}
    assert state.get_series_state(1) == SeriesState()
    assert 1 in state.series
    assert state.series[1].first_point is None


# ---------------------------------------------------------------------------
# save() tests
# ---------------------------------------------------------------------------


def test_save_writes_actual_file(tmp_path, fixed_now):
    now = fixed_now()
    path = tmp_path / "state.json"
    storage = StateStorage(path)
    wal = Mock()
    wal.read_all.return_value = []
    backend = Mock()
    backend.flush.return_value = Result.ok_payload(0)
    state = State(backend, wal, storage)
    state.series = {1: SeriesState(last_point=now)}

    state.save()

    assert path.exists()
    assert json.loads(path.read_text()) == {
        "1": {"first_point": None, "last_point": now.isoformat(timespec="seconds"), "first_start": None, "last_end": None}
    }


def test_save_does_not_mutate_state():

    backend = Mock()
    backend.flush.return_value = Result(0)
    wal = Mock()
    wal.read_all.return_value = []
    state = State(backend=backend, wal=wal, storage=Mock())
    state.series = {2: SeriesState(last_point=10)}

    before = dict(state.series)

    state.save()

    assert state.series == before

'''

# -------------------
# update after fetch
# -------------------

TODO delete
def test_update_after_fetch_no_new_data(state, fixed_now):

    state.series[1] = SeriesState(last_point=datetime.min)
    now = fixed_now()
    state.update_after_fetch(1, now)
    assert state.series[1].last_end == now


def test_update_when_not_captured(state):
    state.update_after_fetch(2, datetime.min)
    assert state.series[2].last_end == datetime.min
'''

def test_iter_metrics(state, fixed_now):

    first = datetime.min
    between = fixed_now()
    last = datetime.max
    state.series = {
        1: SeriesState(first_point=first, last_point=between),
        2: SeriesState(first_point=between, last_point=last),
    }

    items = list(state.iter_series_state())

    assert (1, SeriesState(first_point=first, last_point=between)) in items
    assert (2, SeriesState(first_point=between, last_point=last)) in items


# --------------------------
# rebuild measurement state
# --------------------------


def test_get_last_point_triggers_rebuild(state, fixed_now):
    now = fixed_now()
    state._rebuild_measurement_state = lambda m: SeriesState(first_point=now, last_point=now)
    state.series = {}

    assert state.get_last_point(1) == now
    assert state.series[1].last_point == now


def test_get_last_timestamp_returns_empty_when_missing(state):
    state._rebuild_measurement_state = lambda m: SeriesState()
    state._state = {}

    assert state.get_last_point(2) is None
    assert 2 in state.series


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
    assert state.series[1] == SeriesState(first_point=datetime.min, last_point=datetime.max, first_start=datetime.min, last_end=datetime.max)


def test_update_range_expands_forward(state):
    first = datetime.min
    current = first + timedelta(days=20)
    range_min = current - timedelta(days=5)
    range_max = current + timedelta(days=10)
    state.series = {1: SeriesState(first_point=first, last_point=current)}
    state.update_range(1, first=range_min, last=range_max)
    assert state.series[1] == SeriesState(first_point=first, last_point=range_max, first_start=first, last_end=range_max)


def test_update_range_expands_backward(state):
    range_min = datetime.min
    first = range_min + timedelta(days=5)
    current = first + timedelta(days=20)
    state.series = {1: SeriesState(first_point=first, last_point=current)}
    state.update_range(1, first=range_min, last=current)
    assert state.series[1] == SeriesState(first_point=range_min, last_point=current, first_start=range_min, last_end=current)


def test_update_range_does_not_shrink(state):
    first = datetime.min
    current = first + timedelta(days=10)
    range_min = first + timedelta(days=2)
    range_max = current - timedelta(days=2)
    state.series = {1: SeriesState(first_point=first, last_point=current)}
    state.update_range(1, first=range_min, last=range_max)
    assert state.series[1] == SeriesState(first_point=first, last_point=current, first_start=first, last_end=current)

