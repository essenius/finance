from pathlib import Path
from unittest.mock import Mock

from finance.state.manager import State

# ---------------------------------------------------------------------------
# Constructor tests
# ---------------------------------------------------------------------------


def test_state_constructor_loads_initial_state(monkeypatch):
    """State should load initial state via load_state()."""

    fake_state = {"spx": {"fields": {"v": 1}, "last_timestamp": 10}}
    monkeypatch.setattr("finance.state.manager.load_state", lambda p: fake_state)

    state = State(Mock(), Mock(), path=Path("/tmp/x"))

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
    ts.write.return_value = {"ok": True}

    result = state.ingest(entry)

    wal.enqueue.assert_called_once_with(entry)
    assert state.data["spx"] == {"fields": {"v": 1}, "last_timestamp": 100}
    assert result["ok"] is True


def test_ingest_flushes_fifo_until_empty(state_env, make_entry, wal_sequence, two_wal_entries_with_none):
    state, ts, wal, path = state_env

    # WAL contains two older entries + new one
    wal_sequence(wal, two_wal_entries_with_none())

    ts.write.return_value = {"ok": True}

    state.ingest(make_entry("a", 3, 30))

    assert ts.write.call_count == 2
    assert wal.dequeue.call_count == 2


def test_ingest_stops_on_first_failure(state_env, make_entry, wal_sequence, two_wal_entries):
    state, ts, wal, path = state_env

    wal_sequence(wal, two_wal_entries())

    ts.write.side_effect = [{"ok": False, "error": "down"}]

    result = state.ingest(make_entry("a", 3, 30))

    assert result["ok"] is False
    assert "failed to write" in result["reason"]
    wal.dequeue.assert_not_called()


def test_ingest_keeps_state_updated_even_on_failure(state_env, make_entry, wal_sequence, two_wal_entries):
    state, ts, wal, path = state_env

    # WAL contains an older entry that will fail to flush
    wal_sequence(wal, two_wal_entries())

    ts.write.return_value = {"ok": False, "error": "down"}

    result = state.ingest(make_entry("x", 10, 100))

    assert state.data["x"] == {"fields": {"v": 10}, "last_timestamp": 100}
    assert result["ok"] is False
    wal.enqueue.assert_called_once()


def test_ingest_flushes_remaining_after_recovery(state_env, make_entry, wal_sequence, two_wal_entries_with_none):
    state, ts, wal, path = state_env

    wal_sequence(wal, two_wal_entries_with_none())

    ts.write.side_effect = [
        {"ok": False, "error": "down"},  # first attempt fails
        {"ok": True},                    # retry succeeds
        {"ok": True},                    # next entry succeeds
    ]

    entry = make_entry("a", 3, 30)
    # First ingest fails
    result1 = state.ingest(entry)
    assert result1["ok"] is False

    # WAL still contains entries
    assert wal.dequeue.call_count == 0

    # Second ingest should flush everything
    wal_sequence(wal, two_wal_entries_with_none())

    result2 = state.ingest(entry)
    assert result2["ok"] is True
    assert wal.dequeue.call_count == 2


# ---------------------------------------------------------------------------
# save() tests
# ---------------------------------------------------------------------------


def test_save_writes_actual_file(tmp_path):
    path = tmp_path / "state.json"

    state = State(timeseries_client=Mock(), wal=Mock(), path=path)
    state._state = {"gold": {"fields": {"v": 2000}, "last_timestamp": 50}}

    state.save()

    assert path.exists()
    import json
    assert json.loads(path.read_text()) == {
        "gold": {"fields": {"v": 2000}, "last_timestamp": 50}
    }


def test_save_does_not_mutate_state(tmp_path):
    path = tmp_path / "state.json"

    state = State(timeseries_client=Mock(), wal=Mock(), path=path)
    state._state = {"x": {"fields": {"v": 1}, "last_timestamp": 10}}

    before = dict(state._state)

    state.save()

    assert state._state == before
