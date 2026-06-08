# Copyright 2026 Rik Essenius
# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.
# File: tests/state/test_state.py

import json
import time
from unittest.mock import Mock

from finance.common.model import FetchResult, TimeseriesResult, TimeseriesWrite
from finance.state.manager import State

# ---------------------------------------------------------------------------
# Constructor tests
# ---------------------------------------------------------------------------


def test_state_constructor_loads_initial_state(monkeypatch, tmp_path):
    """State should load initial state via load_state()."""

    fake_state = {"spx": {"fields": {"v": 1}, "last_timestamp": 10}}
    monkeypatch.setattr("finance.state.manager.load_state", lambda p: fake_state)

    path = tmp_path / "state.json"
    state = State(Mock(), Mock(), path=path, bucket_for=lambda m: "bucket")

    assert state.data == fake_state


# ---------------------------------------------------------------------------
# get() tests
# ---------------------------------------------------------------------------


def test_get_returns_cached_entry(state_env):
    """If measurement exists in state, return it without rebuild."""

    state, ts, wal, path = state_env
    state._state = {"spx": {"fields": {"v": 1}, "last_timestamp": 10}}

    result = state.get("spx")

    assert result == {"fields": {"v": 1}, "last_timestamp": 10}
    wal.read_all.assert_not_called()
    ts.query_latest.assert_not_called()


def test_get_triggers_rebuild_when_missing(monkeypatch, mock_rebuild, state_env):
    """If measurement missing, State should call rebuild_measurement_state()."""

    state, _, _, _ = state_env
    mock_rebuild({"fields": {"v": 999}, "last_timestamp": 123})
    state._state = {}

    result = state.get("spx")

    assert result == {"fields": {"v": 999}, "last_timestamp": 123}
    assert state.data["spx"] == result


def test_get_returns_none_when_rebuild_finds_nothing(monkeypatch, mock_rebuild, state_env):

    state, _, _, _ = state_env
    mock_rebuild(None)
    state._state = {}

    assert state.get("spx") is None
    assert "spx" not in state.data


# ---------------------------------------------------------------------------
# ingest() tests
# ---------------------------------------------------------------------------


def test_ingest_enqueues_and_updates_state(state_env, make_entry):
    state, ts, wal, path = state_env

    entry = make_entry()
    ts.write.return_value = TimeseriesResult.ok_payload("spx", entry)

    result = state.ingest(entry)

    wal.enqueue.assert_called_once_with(entry)
    assert state.data["spx"] == {"fields": {"v": 1}, "last_timestamp": 100}
    assert result.ok


def test_ingest_flushes_fifo_until_empty(state_env, make_entry, wal_sequence, two_wal_entries_with_none):
    state, ts, wal, path = state_env

    # WAL contains two older entries + new one
    wal_sequence(wal, two_wal_entries_with_none())

    ts.write.return_value = TimeseriesResult.ok_payload(measurement="a", payload=None)

    state.ingest(make_entry("a", 3, 30))

    assert ts.write.call_count == 2
    assert wal.dequeue.call_count == 2


def test_ingest_stops_on_first_failure(state_env, make_entry, wal_sequence, two_wal_entries):
    state, ts, wal, path = state_env

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
    state, ts, wal, path = state_env

    # WAL contains an older entry that will fail to flush
    wal_sequence(wal, two_wal_entries())

    ts.write.return_value = TimeseriesResult.fail(measurement="x", reason="error", error="down")

    result = state.ingest(make_entry("x", 10, 100))

    assert state.data["x"] == {"fields": {"v": 10}, "last_timestamp": 100}
    assert not result.ok
    wal.enqueue.assert_called_once()


def test_ingest_flushes_remaining_after_recovery(state_env, make_entry, wal_sequence, two_wal_entries_with_none):
    state, ts, wal, path = state_env

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


# ---------------------------------------------------------------------------
# save() tests
# ---------------------------------------------------------------------------


def test_save_writes_actual_file(tmp_path):
    path = tmp_path / "state.json"

    wal = Mock()
    ts = Mock()
    state = State(ts, wal, path, bucket_for=lambda m: "b")
    state._state = {"gold": {"fields": {"v": 2000}, "last_timestamp": 50}}

    state.save()

    assert path.exists()
    assert json.loads(path.read_text()) == {"gold": {"fields": {"v": 2000}, "last_timestamp": 50}}


def test_save_does_not_mutate_state(tmp_path):
    path = tmp_path / "state.json"

    state = State(timeseries_client=Mock(), wal=Mock(), path=path, bucket_for=lambda m: "b")
    state._state = {"x": {"fields": {"v": 1}, "last_timestamp": 10}}

    before = dict(state._state)

    state.save()

    assert state._state == before


def test_update_after_fetch_newer_data(monkeypatch, state_env):
    state, ts, wal, path = state_env

    # existing persisted timestamp
    state._state["spx"] = {"last_timestamp": 100}

    # freeze time
    monkeypatch.setattr(time, "time", lambda: 999)

    result = FetchResult.ok_payload(
        "spx",
        [
            type("Obj", (), {"timestamp": 150}),
            type("Obj", (), {"timestamp": 120}),
        ],
    )

    assert state.update_after_fetch(result) is True
    assert state.data["spx"]["last_try"] == 999
    assert state.data["spx"]["last_timestamp"] == 100  # unchanged


def test_update_after_fetch_no_new_data(monkeypatch, state_env):
    state, ts, wal, path = state_env

    state._state["spx"] = {"last_timestamp": 200}

    monkeypatch.setattr(time, "time", lambda: 1000)

    result = FetchResult.ok_payload(
        "spx",
        [
            type("Obj", (), {"timestamp": 150}),
            type("Obj", (), {"timestamp": 180}),
        ],
    )

    assert state.update_after_fetch(result) is False
    assert state.data["spx"]["last_try"] == 1000


def test_update_after_fetch_failure(monkeypatch, state_env):
    state, ts, wal, path = state_env

    monkeypatch.setattr(time, "time", lambda: 777)

    result = FetchResult.fail("spx", "boom")

    assert state.update_after_fetch(result) is False
    assert state.data["spx"]["last_try"] == 777


def test_iter_metrics(state_env):
    state, ts, wal, path = state_env

    state._state = {
        "a": {"fields": {"x": 1}, "last_timestamp": 10},
        "b": {"fields": {"y": 2}, "last_timestamp": 20},
    }

    items = list(state.iter_metrics())

    assert ("a", {"fields": {"x": 1}, "last_timestamp": 10}) in items
    assert ("b", {"fields": {"y": 2}, "last_timestamp": 20}) in items


def test_get_last_timestamp_triggers_rebuild(monkeypatch, state_env):
    state, ts, wal, path = state_env

    monkeypatch.setattr(
        "finance.state.manager.rebuild_measurement_state",
        lambda bucket, m, w, t: {"fields": {"v": 1}, "last_timestamp": 123},
    )

    assert state.get_last_timestamp("spx") == 123
    assert state.data["spx"]["last_timestamp"] == 123


def test_get_last_timestamp_returns_none_when_missing(state_env, monkeypatch):
    state, ts, wal, path = state_env

    # Ensure state is empty and rebuild returns nothing
    state._state = {}
    monkeypatch.setattr(
        "finance.state.manager.rebuild_measurement_state",
        lambda bucket, m, w, t: None,
    )

    result = state.get_last_timestamp("spx")

    assert result is None
    assert "spx" not in state.data


def test_update_composite(state_env):
    state, ts, wal, path = state_env

    state.update_composite("comp", {"v": 42}, 999)

    assert state.data["comp"] == {
        "fields": {"v": 42},
        "last_timestamp": 999,
    }


def test_ingest_first_time(state_env, unwrap):
    state, _, wal, _ = state_env
    write = TimeseriesWrite("eurusd", {"price": 1.10}, {}, 1000, "b")
    result = state.ingest(write)

    payload = unwrap(result)
    assert payload is write
    assert result.meta == {"skipped": False, "reason": "first-time"}
    assert state._state["eurusd"]["last_timestamp"] == 1000
    wal.enqueue.assert_called_once()


def test_ingest_new_write(state_env):
    state, _, wal, _ = state_env
    state._state["eurusd"] = {"last_timestamp": 1000}

    write = TimeseriesWrite("eurusd", {"price": 1.11}, {}, 2000, "b")
    result = state.ingest(write)

    assert result.ok is True
    assert result.payload == write
    assert result.meta == {"skipped": False, "reason": "new"}
    assert state._state["eurusd"]["last_timestamp"] == 2000
    wal.enqueue.assert_called_once()


def test_ingest_skip_unchanged(state_env):
    state, _, wal, _ = state_env
    state._state["eurusd"] = {"last_timestamp": 1000}

    write = TimeseriesWrite("eurusd", {"price": 1.10}, {}, 1000, "b")
    result = state.ingest(write)

    assert result.ok is True
    assert result.payload is None
    assert result.meta == {"skipped": True, "reason": "unchanged"}
    assert state._state["eurusd"]["last_timestamp"] == 1000
    wal.enqueue.assert_not_called()


def test_ingest_skip_older(state_env):
    state, _, wal, _ = state_env
    state._state["eurusd"] = {"last_timestamp": 2000}

    write = TimeseriesWrite("eurusd", {"price": 1.09}, {}, 1000, "b")
    result = state.ingest(write)

    assert result.ok is True
    assert result.payload is None
    assert result.meta == {"skipped": True, "reason": "older"}
    assert state._state["eurusd"]["last_timestamp"] == 2000
    wal.enqueue.assert_not_called()
