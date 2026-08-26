# Copyright 2026 Rik Essenius
# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.
# File: tests/state/test_state.py

from datetime import datetime, timedelta

from finance.common.model import SeriesState
from finance.common.time_utils import UTC
from finance.common.types import Failure, Success

# ---------------------------------------------------------------------------
# get() tests
# ---------------------------------------------------------------------------


def test_get_returns_cached_entry(state_env):
    """If measurement exists in state, return it without rebuild."""

    state, backend, wal = state_env
    timestamp = datetime.fromtimestamp(10).astimezone(UTC)
    my_state = SeriesState(first_point=timestamp, last_point=timestamp)
    state.series = {1: my_state}
    result = state.get_series_state(1)
    assert result == my_state
    wal.read_all.assert_not_called()
    backend.read_first.assert_not_called()


def test_get_returns_none_when_rebuild_finds_empty(state):
    state._rebuild_measurement_state = state._rebuild_measurement_state = lambda m: SeriesState()
    state.series = {}
    assert state.get_series_state(1) == SeriesState()
    assert 1 in state.series
    assert state.series[1].first_point is None


# ---------------------------------------------------------------------------
# save() tests
# ---------------------------------------------------------------------------


def test_save_writes_actual_file(state_env, ts):

    state, backend, wal = state_env

    backend.flush.return_value = Success(0)
    backend.save_sweep.return_value = None
    state.series = {
        1: SeriesState(needs_save=True, sweep_start=ts(0), next_sweep=ts(0)),
        2: SeriesState(needs_save=False),
    }

    state.save()
    assert backend.save_sweep.call_count == 1
    assert not state.series[1].needs_save


def test_iter_metrics(state, fixed_now):

    first = datetime.min
    between = fixed_now()
    last = datetime.max
    state.series = {
        1: SeriesState(first_point=first, last_point=between),
        2: SeriesState(first_point=between, last_point=last),
    }
    items = list(state.series.items())

    assert (1, SeriesState(first_point=first, last_point=between)) in items
    assert (2, SeriesState(first_point=between, last_point=last)) in items


# ---------------------------------------
# update composite removed from V1 scope
# ---------------------------------------
"""
TODO re-introduce after v1

def test_update_composite(state):
    state.update_composite("comp", {"v": 42}, 999)

    assert state.series["comp"] == {
        "fields": {"v": 42},
        "last_timestamp": 999,
    }
"""
# -------------
# Update state
# -------------


def test_update_state_save_sweep(state_env, ts):
    state, backend, _ = state_env
    backend.save_sweep.return_value = None
    state.series = {1: SeriesState(needs_save=True, next_sweep=ts(0), sweep_start=ts(0))}
    state.update_state(1, first=datetime.min, last=datetime.max)
    assert not state.series[1].needs_save
    assert backend.save_sweep.call_count == 1


def test_update_state_expands_forward(state):
    first = datetime.min
    current = first + timedelta(days=20)
    range_min = current - timedelta(days=5)
    range_max = current + timedelta(days=10)
    state.series = {1: SeriesState(first_point=first, last_point=current)}
    state.update_state(1, first=range_min, last=range_max)
    series_state = state.series[1]
    assert series_state.first_point, series_state.last_point == (first, range_max)


def test_update_state_expands_backward(state):
    range_min = datetime.min
    first = range_min + timedelta(days=5)
    current = first + timedelta(days=20)
    state.series = {1: SeriesState(first_point=first, last_point=current)}
    state.update_state(1, first=range_min, last=current)
    series_state = state.series[1]
    assert series_state.first_point, series_state.last_point == (range_min, current)


def test_update_state_does_not_shrink(state):
    first = datetime.min
    current = first + timedelta(days=10)
    range_min = first + timedelta(days=2)
    range_max = current - timedelta(days=2)
    state.series = {1: SeriesState(first_point=first, last_point=current)}
    state.update_state(1, first=range_min, last=range_max)
    series_state = state.series[1]
    assert series_state.first_point, series_state.last_point == (first, current)


def test_load_backend_error(state_env, assert_error):

    state, backend, wal = state_env
    backend.get_series_states.return_value = Failure(reason="Boom!", error="Server down")
    backend.flush.return_value = Success(0)
    result = state.load()
    assert_error(result, "Boom!", "Server down")
