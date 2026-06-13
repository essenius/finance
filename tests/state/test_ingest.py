# Copyright 2026 Rik Essenius
# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.
# File: tests/state/test_ingest.py

from finance.common.model import TimeseriesResult, TimeseriesWrite


def test_ingest_enqueues_and_does_not_update_state(state_env, make_entry):
    state, ts, wal, _ = state_env

    entry = make_entry()
    ts.write.return_value = TimeseriesResult.ok_payload("spx", entry)

    result = state.ingest(entry)

    wal.enqueue.assert_called_once_with(entry)
    # this should not write timestamps, happens separately after ingesting the batch
    assert state.data["spx"] == {"fields": {"v": 1}}
    assert result.ok


def test_ingest_flushes_fifo_until_empty(state_env, make_entry, wal_sequence, two_wal_entries_with_none):
    state, ts, wal, _ = state_env

    # WAL contains two older entries + new one
    wal_sequence(wal, two_wal_entries_with_none())

    ts.write.return_value = TimeseriesResult.ok_payload(measurement="a", payload=None)

    state.ingest(make_entry("a", 3, 30))

    assert ts.write.call_count == 2
    assert wal.dequeue.call_count == 2


def test_ingest_stops_on_first_failure(state_env, make_entry, wal_sequence, two_wal_entries):
    state, ts, wal, _ = state_env

    wal_sequence(wal, two_wal_entries())

    ts.write.return_value = TimeseriesResult.fail(
        measurement="a", reason="down", error="x", meta={"failed_timestamp": 100}
    )

    result = state.ingest(make_entry("a", 3, 30))

    assert not result.ok
    assert result.reason == "down"
    assert result.error == "x"
    assert result.meta["failed_timestamp"] == 100
    wal.dequeue.assert_not_called()


def test_ingest_keeps_state_updated_even_on_failure(state_env, make_entry, wal_sequence, two_wal_entries):
    state, ts, wal, _ = state_env

    # WAL contains an older entry that will fail to flush
    wal_sequence(wal, two_wal_entries())

    ts.write.return_value = TimeseriesResult.fail(measurement="x", reason="error", error="down")

    result = state.ingest(make_entry("x", 10, 100))

    assert state.data["x"] == {"fields": {"v": 10}}
    assert not result.ok
    wal.enqueue.assert_called_once()


def test_ingest_flushes_remaining_after_recovery(state_env, make_entry, wal_sequence, two_wal_entries_with_none):
    state, ts, wal, _ = state_env

    entries = two_wal_entries_with_none()
    wal_sequence(wal, entries)
    w1, w2, _ = entries
    ts.write.side_effect = [
        TimeseriesResult.fail(w1.measurement, "down"),  # first attempt fails
        TimeseriesResult.ok_payload(w1.measurement, w1),  # retry succeeds
        TimeseriesResult.ok_payload(w2.measurement, w2),  # next entry succeeds
    ]

    entry = make_entry(measurement="a", value=3, timestamp=30)
    # First ingest fails
    result1 = state.ingest(entry)
    assert not result1.ok
    assert wal.dequeue.call_count == 0

    # Second ingest should flush everything
    wal_sequence(wal, entries)

    entry2 = make_entry(measurement="a", value=4, timestamp=40)
    result2 = state.ingest(entry2)
    assert result2.ok
    assert wal.dequeue.call_count == 2


def test_ingest_first_time(state_env, unwrap):
    state, _, wal, _ = state_env
    write = TimeseriesWrite("eurusd", {"price": 1.10}, {}, 1000, "b")
    result = state.ingest(write)

    payload = unwrap(result)
    assert payload is write
    assert result.meta == {"skipped": False, "reason": "first"}
    wal.enqueue.assert_called_once()


def test_ingest_no_first_timestamp(state_env):
    state, _, wal, _ = state_env
    # inconsistent state, should treat last as None
    state._state["eurusd"] = {"last_timestamp": 1000}

    write = TimeseriesWrite("eurusd", {"price": 1.11}, {}, 1000, "b")
    result = state.ingest(write)

    assert result.ok is True
    assert result.payload == write
    assert result.meta == {"skipped": False, "reason": "first"}
    wal.enqueue.assert_called_once()


def test_ingest_no_last_timestamp(state_env):
    state, _, wal, _ = state_env
    # inconsistent state, should treat last as None
    state._state["eurusd"] = {"first_timestamp": 0}

    write = TimeseriesWrite("eurusd", {"price": 1.11}, {}, 0, "b")
    result = state.ingest(write)

    assert result.ok is True
    assert result.payload == write
    assert result.meta == {"skipped": False, "reason": "first"}
    wal.enqueue.assert_called_once()


def test_ingest_new_write(state_env):
    state, _, wal, _ = state_env
    state._state["eurusd"] = {"first_timestamp": 0, "last_timestamp": 1000}

    write = TimeseriesWrite("eurusd", {"price": 1.11}, {}, 2000, "b")
    result = state.ingest(write)

    assert result.ok is True
    assert result.payload == write
    assert result.meta == {"skipped": False, "reason": "new"}
    wal.enqueue.assert_called_once()


def test_ingest_skip_unchanged(state_env):
    state, _, wal, _ = state_env
    state._state["eurusd"] = {"first_timestamp": 0, "last_timestamp": 1000}

    write = TimeseriesWrite("eurusd", {"price": 1.10}, {}, 1000, "b")
    result = state.ingest(write)

    assert result.ok is True
    assert result.payload is None
    assert result.meta == {"skipped": True, "reason": "unchanged"}
    wal.enqueue.assert_not_called()


def test_ingest_skip_in_range(state_env):
    state, _, wal, _ = state_env
    state._state["eurusd"] = {"first_timestamp": 0, "last_timestamp": 2000}

    write = TimeseriesWrite("eurusd", {"price": 1.09}, {}, 1000, "b")
    result = state.ingest(write)

    assert result.ok is True
    assert result.payload is None
    assert result.meta == {"skipped": True, "reason": "inside-window"}
    wal.enqueue.assert_not_called()


def test_ingest_before_range(state_env):
    state, _, wal, _ = state_env
    state._state["eurusd"] = {"first_timestamp": 1000, "last_timestamp": 2000}

    write = TimeseriesWrite("eurusd", {"price": 1.09}, {}, 500, "b")
    result = state.ingest(write)

    assert result.ok is True
    assert result.payload == write
    assert result.meta == {"skipped": False, "reason": "before-window"}
    wal.enqueue.assert_called_once()
