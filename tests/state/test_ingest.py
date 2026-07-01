# Copyright 2026 Rik Essenius
# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.
# File: tests/state/test_ingest.py

from dataclasses import replace

from finance.common.model import Result, SeriesState


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

    # WAL contains two older entries + new one
    wal.read_all.return_value = two_wal_entries()
    backend.add.return_value = Result.ok_payload(1)
    flush_count = unwrap(state.load())
    assert flush_count == 2
    assert wal.is_empty(), "Wal is empty"
    assert backend.add.call_count == 2, "add call count"
    assert wal.dequeue_multiple.call_count == 2


def test_load_stops_on_first_failure(state_env, two_wal_entries, assert_error):
    state, backend, wal, _ = state_env

    wal.read_all.return_value=two_wal_entries()

    backend.add.return_value = Result.fail(reason="down", error="x", meta={"failed_timestamp": 100})
    result = state.load()
    assert_error(result, "down", "x")
    assert result.meta["failed_timestamp"] == 100
    wal.dequeue_multiple.assert_not_called()

'''
def test_ingest_keeps_state_updated_even_on_failure(state_env, make_entry, wal_sequence, two_wal_entries):
    state, ts, wal, _ = state_env

    # WAL contains an older entry that will fail to flush
    wal_sequence(wal, two_wal_entries())

    ts.add.return_value = SeriesResult.fail(series_name="x", reason="error", error="down")

    result = state.ingest(**make_entry(2, 10, 100))

    assert state.series == {}
    assert not result.ok
    wal.enqueue.assert_called_once()


def test_ingest_flushes_remaining_after_recovery(state_env, make_entry, wal_sequence, two_wal_entries_with_none):
    state, backend, wal, _ = state_env

    entries = two_wal_entries_with_none()
    wal_sequence(wal, entries)
    w1, w2, _ = entries
    backend.add.side_effect = [
        SeriesResult.fail(w1["series"].name, "down"),  # first attempt fails
        SeriesResult.ok_payload(w1["series"].name, 0),  # retry succeeds, but nothing written
        SeriesResult.ok_payload(w2["series"].name, 2),  # next entry succeeds, two written
    ]

    entry = make_entry(value=3, timestamp=30)
    # First ingest fails
    result1 = state.ingest(**entry)
    assert not result1.ok
    assert wal.dequeue_multiple.call_count == 0

    # Second ingest should flush everything
    wal_sequence(wal, entries)

    entry2 = make_entry(value=4, timestamp=40)
    result2 = state.ingest(**entry2)
    assert result2.ok
    assert wal.dequeue_multiple.call_count == 2
'''

def test_ingest_first_time(state_env, make_entry, unwrap):
    state, backend, wal, _ = state_env
    backend.add.return_value = Result.ok_payload(0)

    args = make_entry(timestamp=1000)
    write = replace(args["point"], value=1.11)

    result = state.ingest(args["series"], write)

    payload = unwrap(result)
    assert payload == 0
    assert result.meta == {"skipped": False, "reason": "first"}
    wal.enqueue.assert_called_once()


def test_ingest_no_first_timestamp(state_env, make_entry):
    state, backend, wal, _ = state_env
    backend.add.return_value = Result.ok_payload(0)
    # inconsistent state, should treat last as None
    state.series[1] = SeriesState(last_time=1000)
    args = make_entry(timestamp=1000)
    write = replace(args["point"], value=1.11)

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
    write = replace(args["point"], value=1.11)

    result = state.ingest(args["series"], write)

    assert result.ok is True
    assert result.payload == 0
    assert result.meta == {"skipped": False, "reason": "first"}
    wal.enqueue.assert_called_once()


def test_ingest_new_write_with_flush(state_env, make_entry):
    state, backend, wal, _ = state_env
    backend.add.return_value = Result.ok_payload(1)

    state.series[1] = SeriesState(first_time=0, last_time=1000)

    args = make_entry(timestamp=2000)
    write = replace(args["point"], value=1.11)
    result = state.ingest(args["series"], write)

    assert result.ok is True
    assert result.payload == 1
    assert result.meta == {"skipped": False, "reason": "new"}
    wal.enqueue.assert_called_once()


def test_ingest_skip_unchanged(state_env, make_entry):
    state, _, wal, _ = state_env
    state.series[1] = SeriesState(first_time=0, last_time=1000)

    args = make_entry(timestamp=1000)
    write = replace(args["point"], value=1.10)

    result = state.ingest(args["series"], write)

    assert result.ok is True
    assert result.payload == 0
    assert result.meta == {"skipped": True, "reason": "unchanged"}
    wal.enqueue.assert_not_called()


def test_ingest_skip_in_range(state_env, make_entry):
    state, _, wal, _ = state_env
    state.series[1] = SeriesState(first_time=0, last_time=2000)

    args = make_entry(timestamp=1000)
    write = replace(args["point"], value=1.09)

    result = state.ingest(args["series"], write)

    assert result.ok is True
    assert result.payload == 0
    assert result.meta == {"skipped": True, "reason": "inside-window"}
    wal.enqueue.assert_not_called()


def test_ingest_before_range(state_env, make_entry):
    state, backend, wal, _ = state_env
    backend.add.return_value = Result.ok_payload(1)
    state.series[1] = SeriesState(first_time=1000, last_time=2000)

    args = make_entry(timestamp=500)
    write = replace(args["point"], value=1.09)

    result = state.ingest(args["series"], write)

    assert result.ok is True
    assert result.payload == 1
    assert result.meta == {"skipped": False, "reason": "before-window"}
    wal.enqueue.assert_called_once()


def test_sync_backend_different_counts(state_env, make_entry, unwrap):
    state, backend, wal, _ = state_env
    backend.add.return_value = Result.ok_payload(1)
    wal.dequeue_multiple.side_effect = None
    wal.dequeue_multiple.return_value = 0
    args = make_entry(timestamp=1000)
    write = replace(args["point"], value=1.11)

    result = state.ingest(args["series"], write)

    payload = unwrap(result)
    # dequeue_multiple reported 0 were removed
    assert payload == 0
    assert result.warnings[0] == "Requested to remove 1 entries from the WAL but removed 0"
    assert result.meta == {"skipped": False, "reason": "first"}
    wal.enqueue.assert_called_once()
