# Copyright 2026 Rik Essenius
# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.
# File: tests/state/test_ingest.py

from dataclasses import replace
from datetime import datetime

from finance.common.model import SeriesPoint, SeriesState
from finance.common.types import Failure, Success, Unwrap
from tests.support.types import AssertError, Creator, Factory, StateContext, WalContext


def test_ingest_enqueues_and_does_not_update_state(make_entry: Creator[WalContext], state_env: StateContext):
    state, backend, wal = state_env

    point = make_entry().point
    backend.add_point.return_value = Success(0)

    result = state.ingest(point)

    wal.enqueue.assert_called_once_with(point)
    assert result.ok is True
    # nothing dequeued as backend reported nothing written
    wal.dequeue_multiple.assert_called_with(0)

    # this should not write timestamps, happens separately after ingesting the batch
    assert state.series_state.get(1) is None


def test_ingest_enqueues_and_removes_wal_entry(make_entry: Creator[WalContext], state_env: StateContext):
    state, backend, wal = state_env

    point = make_entry().point
    backend.add_point.return_value = Success(1)

    result = state.ingest(point)

    wal.enqueue.assert_called_once_with(point)
    assert result.ok is True
    # nothing dequeued as backend reported nothing written
    wal.dequeue_multiple.assert_called_with(1)
    # this should not write timestamps
    assert state.series_state.get(1) is None


def test_load_flushes_fifo_until_empty(
    state_env: StateContext, two_wal_entries: Factory[list[SeriesPoint]], unwrap: Unwrap[int]
):
    state, backend, wal = state_env

    wal.read_all.side_effect = [
        two_wal_entries(),  # first call
        two_wal_entries(),  # second call
        [],  # second call
    ]
    backend.add_point.side_effect = [Success(1), Success(0)]
    backend.get_series_states.return_value = Success({})
    backend.flush.return_value = Success(1)
    flush_count = unwrap(state.load())
    assert flush_count == 2, "flush count"
    assert wal.is_empty(), "Wal is empty"
    assert backend.add_point.call_count == 2, "add call count"
    assert wal.dequeue_multiple.call_count == 3, "dequeue called 3 times (1, 0, 1)"


def test_load_stops_on_first_failure(
    assert_error: AssertError, state_env: StateContext, two_wal_entries: Factory[list[SeriesPoint]]
):
    state, backend, wal = state_env

    wal.read_all.return_value = two_wal_entries()

    backend.add_point.return_value = Failure(reason="down", error="x", meta={"failed_timestamp": 600})
    backend.get_series_states.return_value = Success({})

    result = state.load()
    assert_error(result, "down", "x")
    assert result.meta is not None
    assert result.meta["failed_timestamp"] == 600
    wal.dequeue_multiple.assert_not_called()


def test_ingest_first_point(make_entry: Creator[WalContext], state_env: StateContext, unwrap: Unwrap[int]):
    state, backend, wal = state_env
    backend.add_point.return_value = Success(0)

    point = make_entry(timestamp=1200).point
    write = replace(point, close=1.11)

    result = state.ingest(write)

    payload = unwrap(result)
    assert payload == 0
    wal.enqueue.assert_called_once()


def test_ingest_no_first_timestamp(make_entry: Creator[WalContext], state_env: StateContext, ts: Creator[datetime]):
    state, backend, wal = state_env
    backend.add_point.return_value = Success(0)
    # inconsistent state, should treat last as None
    state.series_state[1] = SeriesState(last_point=ts(1200))
    point = make_entry(timestamp=1200).point
    write = replace(point, close=1.11)

    result = state.ingest(write)

    assert result.ok is True
    assert result.payload == 0
    wal.enqueue.assert_called_once()


def test_ingest_no_last_timestamp(make_entry: Creator[WalContext], state_env: StateContext, ts: Creator[datetime]):
    state, backend, wal = state_env
    backend.add_point.return_value = Success(0)
    # inconsistent state, should treat last as None
    state.series_state[1] = SeriesState(first_point=ts(0))

    point = make_entry(timestamp=0).point
    write = replace(point, close=1.11)

    result = state.ingest(write)

    assert result.ok is True
    assert result.payload == 0
    wal.enqueue.assert_called_once()


def test_ingest_new_write_with_flush(
    make_entry: Creator[WalContext], make_series_state: Creator[SeriesState], state_env: StateContext
):
    state, backend, wal = state_env
    backend.add_point.return_value = Success(1)

    state.series_state[1] = make_series_state()

    point = make_entry(timestamp=1800).point
    write = replace(point, close=1.11)
    result = state.ingest(write)

    assert result.ok is True
    assert result.payload == 1
    wal.enqueue.assert_called_once()


def test_ingest_in_range(
    make_entry: Creator[WalContext], make_series_state: Creator[SeriesState], state_env: StateContext
):
    state, backend, wal = state_env
    backend.add_point.return_value = Success(2)

    state.series_state[1] = make_series_state(start=0, end=1800)

    point = make_entry(timestamp=1200).point
    write = replace(point, close=1.09)

    result = state.ingest(write)

    assert result.ok is True
    assert result.payload == 2
    wal.enqueue.assert_called_once()


def test_ingest_before_range(
    make_entry: Creator[WalContext], make_series_state: Creator[SeriesState], state_env: StateContext
):
    state, backend, wal = state_env
    backend.add_point.return_value = Success(1)
    state.series_state[1] = make_series_state(start=1200, end=1800)

    point = make_entry(timestamp=600).point
    write = replace(point, close=1.09)

    result = state.ingest(write)

    assert result.ok is True
    assert result.payload == 1
    wal.enqueue.assert_called_once()


def test_sync_backend_different_counts(make_entry: Creator[WalContext], state_env: StateContext, unwrap: Unwrap[int]):
    state, backend, wal = state_env
    backend.add_point.return_value = Success(1)
    wal.dequeue_multiple.side_effect = None
    wal.dequeue_multiple.return_value = 0
    point = make_entry(timestamp=1200).point
    write = replace(point, close=1.11)

    result = state.ingest(write)

    payload = unwrap(result)
    # dequeue_multiple reported 0 were removed
    assert payload == 0
    assert result.warnings[0] == "Requested to remove 1 entries from the WAL but removed 0"
    wal.enqueue.assert_called_once()
