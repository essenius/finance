# Copyright 2026 Rik Essenius
# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.
# File: tests/state/test_ingest.py

from dataclasses import replace
from datetime import UTC, datetime

from finance.common.model import SeriesState
from finance.common.result import Failure, Success


def make_series_state(start: int = 0, end: int = 1200) -> SeriesState:
    return SeriesState(
        first_point=datetime.fromtimestamp(start, tz=UTC), last_point=datetime.fromtimestamp(end, tz=UTC)
    )


def test_ingest_enqueues_and_does_not_update_state(state_env, make_entry):
    state, backend, wal = state_env

    args = make_entry()
    backend.add_point.return_value = Success(0)

    result = state.ingest(args["point"])

    wal.enqueue.assert_called_once_with(args["point"])
    assert result.ok
    # nothing dequeued as backend reported nothing written
    wal.dequeue_multiple.assert_called_with(0)

    # this should not write timestamps, happens separately after ingesting the batch
    assert state.series.get(1) is None


def test_ingest_enqueues_and_removes_wal_entry(state_env, make_entry):
    state, backend, wal = state_env

    args = make_entry()
    backend.add_point.return_value = Success(1)

    result = state.ingest(args["point"])

    wal.enqueue.assert_called_once_with(args["point"])
    assert result.ok
    # nothing dequeued as backend reported nothing written
    wal.dequeue_multiple.assert_called_with(1)
    # this should not write timestamps
    assert state.series.get(1) is None


def test_load_flushes_fifo_until_empty(state_env, two_wal_entries, unwrap):
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


def test_load_stops_on_first_failure(state_env, two_wal_entries, assert_error):
    state, backend, wal = state_env

    wal.read_all.return_value = two_wal_entries()

    backend.add_point.return_value = Failure(reason="down", error="x", meta={"failed_timestamp": 600})
    backend.get_series_states.return_value = Success({})

    result = state.load()
    assert_error(result, "down", "x")
    assert result.meta["failed_timestamp"] == 600
    wal.dequeue_multiple.assert_not_called()


def test_ingest_first_point(state_env, make_entry, unwrap):
    state, backend, wal = state_env
    backend.add_point.return_value = Success(0)

    args = make_entry(timestamp=1200)
    write = replace(args["point"], close=1.11)

    result = state.ingest(write)

    payload = unwrap(result)
    assert payload == 0
    wal.enqueue.assert_called_once()


def test_ingest_no_first_timestamp(state_env, make_entry):
    state, backend, wal = state_env
    backend.add_point.return_value = Success(0)
    # inconsistent state, should treat last as None
    state.series[1] = SeriesState(last_point=1200)
    args = make_entry(timestamp=1200)
    write = replace(args["point"], close=1.11)

    result = state.ingest(write)

    assert result.ok is True
    assert result.payload == 0
    wal.enqueue.assert_called_once()


def test_ingest_no_last_timestamp(state_env, make_entry):
    state, backend, wal = state_env
    backend.add_point.return_value = Success(0)
    # inconsistent state, should treat last as None
    state.series[1] = SeriesState(first_point=0)

    args = make_entry(timestamp=0)
    write = replace(args["point"], close=1.11)

    result = state.ingest(write)

    assert result.ok is True
    assert result.payload == 0
    wal.enqueue.assert_called_once()


def test_ingest_new_write_with_flush(state_env, make_entry):
    state, backend, wal = state_env
    backend.add_point.return_value = Success(1)

    state.series[1] = make_series_state()

    args = make_entry(timestamp=1800)
    write = replace(args["point"], close=1.11)
    result = state.ingest(write)

    assert result.ok is True
    assert result.payload == 1
    wal.enqueue.assert_called_once()


def test_ingest_in_range(state_env, make_entry):
    state, backend, wal = state_env
    backend.add_point.return_value = Success(2)

    state.series[1] = make_series_state(start=0, end=1800)

    args = make_entry(timestamp=1200)
    write = replace(args["point"], close=1.09)

    result = state.ingest(write)

    assert result.ok is True
    assert result.payload == 2
    wal.enqueue.assert_called_once()


def test_ingest_before_range(state_env, make_entry):
    state, backend, wal = state_env
    backend.add_point.return_value = Success(1)
    state.series[1] = make_series_state(start=1200, end=1800)

    args = make_entry(timestamp=600)
    write = replace(args["point"], close=1.09)

    result = state.ingest(write)

    assert result.ok is True
    assert result.payload == 1
    wal.enqueue.assert_called_once()


def test_sync_backend_different_counts(state_env, make_entry, unwrap):
    state, backend, wal = state_env
    backend.add_point.return_value = Success(1)
    wal.dequeue_multiple.side_effect = None
    wal.dequeue_multiple.return_value = 0
    args = make_entry(timestamp=1200)
    write = replace(args["point"], close=1.11)

    result = state.ingest(write)

    payload = unwrap(result)
    # dequeue_multiple reported 0 were removed
    assert payload == 0
    assert result.warnings[0] == "Requested to remove 1 entries from the WAL but removed 0"
    wal.enqueue.assert_called_once()
