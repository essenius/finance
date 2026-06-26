# Copyright 2026 Rik Essenius
# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.
# File: tests/state/test_ingest.py

from dataclasses import replace

from finance.common.model import SeriesResult, SeriesState


def test_ingest_enqueues_and_does_not_update_state(state_env, make_entry):
    state, backend, wal, _ = state_env

    args = make_entry()
    backend.write.return_value = SeriesResult.ok_payload("spx", args["point"])

    result = state.ingest(**args)

    wal.enqueue.assert_called_once_with(args["point"])
    # this should not write timestamps, happens separately after ingesting the batch
    assert result.ok
    assert state.series.get(1) is None


def test_ingest_flushes_fifo_until_empty(state_env, make_entry, wal_sequence, two_wal_entries_with_none):
    state, backend, wal, _ = state_env

    # WAL contains two older entries + new one
    wal_sequence(wal, two_wal_entries_with_none())

    backend.add.return_value = SeriesResult.ok_payload(series_name="a", payload=None)
    state.ingest(**make_entry(1, 3, 30))

    assert backend.add.call_count == 2, "add call count"
    assert wal.dequeue.call_count == 2, "dequeue call count"


def test_ingest_stops_on_first_failure(state_env, make_entry, wal_sequence, two_wal_entries):
    state, ts, wal, _ = state_env

    wal_sequence(wal, two_wal_entries())

    ts.add.return_value = SeriesResult.fail(series_name="a", reason="down", error="x", meta={"failed_timestamp": 100})

    result = state.ingest(**make_entry(1, 3, 30))

    assert not result.ok
    assert result.reason == "down"
    assert result.error == "x"
    assert result.meta["failed_timestamp"] == 100
    wal.dequeue.assert_not_called()


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
    state, ts, wal, _ = state_env

    entries = two_wal_entries_with_none()
    wal_sequence(wal, entries)
    w1, w2, _ = entries
    ts.add.side_effect = [
        SeriesResult.fail(w1["series"].name, "down"),  # first attempt fails
        SeriesResult.ok_payload(w1["series"].name, w1),  # retry succeeds
        SeriesResult.ok_payload(w2["series"].name, w2),  # next entry succeeds
    ]

    entry = make_entry(value=3, timestamp=30)
    # First ingest fails
    result1 = state.ingest(**entry)
    assert not result1.ok
    assert wal.dequeue.call_count == 0

    # Second ingest should flush everything
    wal_sequence(wal, entries)

    entry2 = make_entry(value=4, timestamp=40)
    result2 = state.ingest(**entry2)
    assert result2.ok
    assert wal.dequeue.call_count == 2


def test_ingest_first_time(state_env, make_entry, unwrap):
    state, _, wal, _ = state_env
    args = make_entry(timestamp=1000)
    write = replace(args["point"], value=1.11)
    result = state.ingest(args["series"], write)

    payload = unwrap(result)
    assert payload is write
    assert result.meta == {"skipped": False, "reason": "first"}
    wal.enqueue.assert_called_once()


def test_ingest_no_first_timestamp(state_env, make_entry):
    state, _, wal, _ = state_env
    # inconsistent state, should treat last as None
    state.series[1] = SeriesState(last_timestamp=1000)
    args = make_entry(timestamp=1000)
    write = replace(args["point"], value=1.11)

    result = state.ingest(args["series"], write)

    assert result.ok is True
    assert result.payload == write
    assert result.meta == {"skipped": False, "reason": "first"}
    wal.enqueue.assert_called_once()


def test_ingest_no_last_timestamp(state_env, make_entry):
    state, _, wal, _ = state_env
    # inconsistent state, should treat last as None
    state.series[1] = SeriesState(first_timestamp=0)

    args = make_entry(timestamp=0)
    write = replace(args["point"], value=1.11)

    result = state.ingest(args["series"], write)

    assert result.ok is True
    assert result.payload == write
    assert result.meta == {"skipped": False, "reason": "first"}
    wal.enqueue.assert_called_once()


def test_ingest_new_write(state_env, make_entry):
    state, _, wal, _ = state_env
    state.series[1] = SeriesState(first_timestamp=0, last_timestamp=1000)

    args = make_entry(timestamp=2000)
    write = replace(args["point"], value=1.11)
    result = state.ingest(args["series"], write)

    assert result.ok is True
    assert result.payload == write
    assert result.meta == {"skipped": False, "reason": "new"}
    wal.enqueue.assert_called_once()


def test_ingest_skip_unchanged(state_env, make_entry):
    state, _, wal, _ = state_env
    state.series[1] = SeriesState(first_timestamp=0, last_timestamp=1000)

    args = make_entry(timestamp=1000)
    write = replace(args["point"], value=1.10)

    result = state.ingest(args["series"], write)

    assert result.ok is True
    assert result.payload is None
    assert result.meta == {"skipped": True, "reason": "unchanged"}
    wal.enqueue.assert_not_called()


def test_ingest_skip_in_range(state_env, make_entry):
    state, _, wal, _ = state_env
    state.series[1] = SeriesState(first_timestamp=0, last_timestamp=2000)

    args = make_entry(timestamp=1000)
    write = replace(args["point"], value=1.09)

    result = state.ingest(args["series"], write)

    assert result.ok is True
    assert result.payload is None
    assert result.meta == {"skipped": True, "reason": "inside-window"}
    wal.enqueue.assert_not_called()


def test_ingest_before_range(state_env, make_entry):
    state, _, wal, _ = state_env
    state.series[1] = SeriesState(first_timestamp=1000, last_timestamp=2000)

    args = make_entry(timestamp=500)
    write = replace(args["point"], value=1.09)

    result = state.ingest(args["series"], write)

    assert result.ok is True
    assert result.payload == write
    assert result.meta == {"skipped": False, "reason": "before-window"}
    wal.enqueue.assert_called_once()
