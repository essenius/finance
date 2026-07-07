# Copyright 2026 Rik Essenius
# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.
# File: tests/state/test_ingest.py

from dataclasses import replace
from datetime import UTC, datetime

from finance.common.model import Result, SeriesState


def make_series_state(start: int = 0, end: int = 1200) -> SeriesState:
    return SeriesState(first_time=datetime.fromtimestamp(start, tz=UTC), last_time=datetime.fromtimestamp(end, tz=UTC))


def test_ingest_enqueues_and_does_not_update_state(state_env, make_entry):
    state, backend, wal, _ = state_env

    args = make_entry()
    backend.add.return_value = Result.ok_payload(0)

    result = state.ingest(**args)

    wal.enqueue.assert_called_once_with(args["point"])
    assert result.ok
    # nothing dequeued as backend reported nothing written
    wal.dequeue_multiple.assert_called_with(0)

    # this should not write timestamps, happens separately after ingesting the batch
    assert state.series.get(1) is None


def test_ingest_enqueues_and_removes_wal_entry(state_env, make_entry):
    state, backend, wal, _ = state_env

    args = make_entry()
    backend.add.return_value = Result.ok_payload(1)

    result = state.ingest(**args)

    wal.enqueue.assert_called_once_with(args["point"])
    assert result.ok
    # nothing dequeued as backend reported nothing written
    wal.dequeue_multiple.assert_called_with(1)
    # this should not write timestamps
    assert state.series.get(1) is None


def test_load_flushes_fifo_until_empty(state_env, two_wal_entries, unwrap):
    state, backend, wal, _ = state_env

    wal.read_all.side_effect = [
        two_wal_entries(),  # first call
        [],  # second call
    ]
    backend.add.side_effect = [Result.ok_payload(1), Result.ok_payload(0)]
    backend.flush.return_value = Result.ok_payload(1)
    flush_count = unwrap(state.load())
    assert flush_count == 2, "flush count"
    assert wal.is_empty(), "Wal is empty"
    assert backend.add.call_count == 2, "add call count"
    assert wal.dequeue_multiple.call_count == 3, "dequeue called 3 times (1, 0, 1)"


def test_load_stops_on_first_failure(state_env, two_wal_entries, assert_error):
    state, backend, wal, _ = state_env

    wal.read_all.return_value = two_wal_entries()

    backend.add.return_value = Result.fail(reason="down", error="x", meta={"failed_timestamp": 600})
    result = state.load()
    assert_error(result, "down", "x")
    assert result.meta["failed_timestamp"] == 600
    wal.dequeue_multiple.assert_not_called()


def test_ingest_first_time(state_env, make_entry, unwrap):
    state, backend, wal, _ = state_env
    backend.add.return_value = Result.ok_payload(0)

    args = make_entry(timestamp=1200)
    write = replace(args["point"], close=1.11)

    result = state.ingest(args["series"], write)

    payload = unwrap(result)
    assert payload == 0
    assert result.meta == {"skipped": False, "reason": "first"}
    wal.enqueue.assert_called_once()


def test_ingest_no_first_timestamp(state_env, make_entry):
    state, backend, wal, _ = state_env
    backend.add.return_value = Result.ok_payload(0)
    # inconsistent state, should treat last as None
    state.series[1] = SeriesState(last_time=1200)
    args = make_entry(timestamp=1200)
    write = replace(args["point"], close=1.11)

    result = state.ingest(args["series"], write)

    assert result.ok is True
    assert result.payload == 0
    assert result.meta == {"skipped": False, "reason": "first"}
    wal.enqueue.assert_called_once()


def test_ingest_no_last_timestamp(state_env, make_entry):
    state, backend, wal, _ = state_env
    backend.add.return_value = Result.ok_payload(0)
    # inconsistent state, should treat last as None
    state.series[1] = SeriesState(first_time=0)

    args = make_entry(timestamp=0)
    write = replace(args["point"], close=1.11)

    result = state.ingest(args["series"], write)

    assert result.ok is True
    assert result.payload == 0
    assert result.meta == {"skipped": False, "reason": "first"}
    wal.enqueue.assert_called_once()


def test_ingest_new_write_with_flush(state_env, make_entry):
    state, backend, wal, _ = state_env
    backend.add.return_value = Result.ok_payload(1)

    state.series[1] = make_series_state()

    args = make_entry(timestamp=1800)
    write = replace(args["point"], close=1.11)
    result = state.ingest(args["series"], write)

    assert result.ok is True
    assert result.payload == 1
    assert result.meta == {"skipped": False, "reason": "new"}
    wal.enqueue.assert_called_once()


def test_ingest_skip_unchanged(state_env, make_entry):
    state, _, wal, _ = state_env
    state.series[1] = make_series_state()

    args = make_entry(timestamp=1200)
    write = replace(args["point"], close=1.10)

    result = state.ingest(args["series"], write)

    assert result.ok is True
    assert result.payload == 0
    assert result.meta == {"skipped": True, "reason": "unchanged"}
    wal.enqueue.assert_not_called()


def test_ingest_skip_in_range(state_env, make_entry):
    state, _, wal, _ = state_env
    state.series[1] = make_series_state(start=0, end=1800)

    args = make_entry(timestamp=1200)
    write = replace(args["point"], close=1.09)

    result = state.ingest(args["series"], write)

    assert result.ok is True
    assert result.payload == 0
    assert result.meta == {"skipped": True, "reason": "inside-window"}
    wal.enqueue.assert_not_called()


def test_ingest_before_range(state_env, make_entry):
    state, backend, wal, _ = state_env
    backend.add.return_value = Result.ok_payload(1)
    state.series[1] = make_series_state(start=1200, end=1800)

    args = make_entry(timestamp=600)
    write = replace(args["point"], close=1.09)

    result = state.ingest(args["series"], write)

    assert result.ok is True
    assert result.payload == 1
    assert result.meta == {"skipped": False, "reason": "before-window"}
    wal.enqueue.assert_called_once()


def test_ingest_misaligned_timestamp(state_env, make_entry):
    state, backend, wal, _ = state_env
    backend.add.return_value = Result.ok_payload(1)
    state.series[1] = make_series_state(start=1200, end=1800)

    # interval is 10m, i.e. 600s
    args = make_entry(timestamp=500)
    write = replace(args["point"], close=1.09)
    result = state.ingest(args["series"], write)

    assert result.ok is True
    assert result.payload == 0
    assert result.meta == {"skipped": True, "reason": "misaligned-interval"}
    wal.enqueue.assert_not_called()


def test_sync_backend_different_counts(state_env, make_entry, unwrap):
    state, backend, wal, _ = state_env
    backend.add.return_value = Result.ok_payload(1)
    wal.dequeue_multiple.side_effect = None
    wal.dequeue_multiple.return_value = 0
    args = make_entry(timestamp=1200)
    write = replace(args["point"], close=1.11)

    result = state.ingest(args["series"], write)

    payload = unwrap(result)
    # dequeue_multiple reported 0 were removed
    assert payload == 0
    assert result.warnings[0] == "Requested to remove 1 entries from the WAL but removed 0"
    assert result.meta == {"skipped": False, "reason": "first"}
    wal.enqueue.assert_called_once()
