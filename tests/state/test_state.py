# Copyright 2026 Rik Essenius
# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.
# File: tests/state/test_state.py

import json
from unittest.mock import Mock

from finance.common.model import FetchResult
from finance.state.state import State
from finance.state.storage import StateStorage

# ---------------------------------------------------------------------------
# get() tests
# ---------------------------------------------------------------------------


def test_get_returns_cached_entry(state_env):
    """If measurement exists in state, return it without rebuild."""

    state, ts, wal, _ = state_env
    state._state = {"spx": {"fields": {"v": 1}, "first_timestamp": 10, "last_timestamp": 10}}

    result = state.get("spx")

    assert result == {"fields": {"v": 1}, "first_timestamp": 10, "last_timestamp": 10}
    wal.read_all.assert_not_called()
    ts.query_latest.assert_not_called()


def test_get_triggers_rebuild_when_missing(state_env):
    """If measurement missing, State should rebuild measurement state."""

    state, _, _, _ = state_env

    state._rebuild_measurement_state = lambda m: {
        "fields": {"v": 999},
        "first_timestamp": 123,
        "last_timestamp": 123,
    }

    state._state = {}

    result = state.get("spx")

    assert result == {
        "fields": {"v": 999},
        "first_timestamp": 123,
        "last_timestamp": 123,
    }
    assert state.data["spx"] == result


def test_get_returns_none_when_rebuild_finds_nothing(state):

    state._rebuild_measurement_state = state._rebuild_measurement_state = lambda m: None
    state._state = {}

    assert state.get("spx") is None
    assert "spx" not in state.data


# ---------------------------------------------------------------------------
# save() tests
# ---------------------------------------------------------------------------


def test_save_writes_actual_file(tmp_path):
    path = tmp_path / "state.json"
    storage = StateStorage(path)
    wal = Mock()
    ts = Mock()
    state = State(ts, wal, storage, bucket_for=lambda m: "b")
    state._state = {"gold": {"fields": {"v": 2000}, "last_timestamp": 50}}

    state.save()

    assert path.exists()
    assert json.loads(path.read_text()) == {"gold": {"fields": {"v": 2000}, "last_timestamp": 50}}


def test_save_does_not_mutate_state(tmp_path):
    # path = tmp_path / "state.json"

    state = State(series_store=Mock(), wal=Mock(), storage=Mock(), bucket_for=lambda m: "b")
    state._state = {"x": {"fields": {"v": 1}, "last_timestamp": 10}}

    before = dict(state._state)

    state.save()

    assert state._state == before


# -------------------
# update after fetch
# -------------------


def test_update_after_fetch_no_new_data(state):

    state._state["spx"] = {"last_timestamp": 200}

    result = FetchResult.ok_payload(
        "spx",
        [
            type("Obj", (), {"timestamp": 150}),
            type("Obj", (), {"timestamp": 180}),
        ],
    )

    state.update_after_fetch(result, 1000)
    assert state.data["spx"]["last_try"] == 1000


def test_update_after_fetch_failure(state):

    result = FetchResult.fail("spx", "boom")
    state.update_after_fetch(result, 777)
    assert state.data["spx"]["last_try"] == 777


def test_iter_metrics(state):

    state._state = {
        "a": {"fields": {"x": 1}, "last_timestamp": 10},
        "b": {"fields": {"y": 2}, "last_timestamp": 20},
    }

    items = list(state.iter_metrics())

    assert ("a", {"fields": {"x": 1}, "last_timestamp": 10}) in items
    assert ("b", {"fields": {"y": 2}, "last_timestamp": 20}) in items


# --------------------------
# rebuild measurement state
# --------------------------


def test_get_last_timestamp_triggers_rebuild(state_env):
    state, ts, wal, path = state_env

    state._rebuild_measurement_state = lambda m: {
        "fields": {"v": 1},
        "first_timestamp": 123,
        "last_timestamp": 123,
    }

    state._state = {}

    assert state.get_last_timestamp("spx") == 123
    assert state.data["spx"]["last_timestamp"] == 123


def test_get_last_timestamp_returns_none_when_missing(state_env):
    state, ts, wal, path = state_env

    state._rebuild_measurement_state = lambda m: None
    state._state = {}

    assert state.get_last_timestamp("spx") is None
    assert "spx" not in state.data


# update composite


def test_update_composite(state_env):
    state, ts, wal, path = state_env

    state.update_composite("comp", {"v": 42}, 999)

    assert state.data["comp"] == {
        "fields": {"v": 42},
        "last_timestamp": 999,
    }


# -------------
# Update range
# -------------


def test_update_range_initializes_missing_timestamps(state):
    state._state = {
        "spx": {
            "fields": {"v": 1},
            # no first_timestamp, no last_timestamp
        }
    }

    state.update_range("spx", first=100, last=200)

    assert state.data["spx"] == {
        "fields": {"v": 1},
        "first_timestamp": 100,
        "last_timestamp": 200,
    }


def test_update_range_expands_forward(state):
    state._state = {
        "spx": {
            "fields": {"v": 1},
            "first_timestamp": 100,
            "last_timestamp": 200,
        }
    }

    state.update_range("spx", first=150, last=300)

    assert state.data["spx"] == {
        "fields": {"v": 1},
        "first_timestamp": 100,  # unchanged
        "last_timestamp": 300,  # expanded
    }


def test_update_range_expands_backward(state):
    state._state = {
        "spx": {
            "fields": {"v": 1},
            "first_timestamp": 100,
            "last_timestamp": 200,
        }
    }

    state.update_range("spx", first=50, last=150)

    assert state.data["spx"] == {
        "fields": {"v": 1},
        "first_timestamp": 50,  # expanded backward
        "last_timestamp": 200,  # unchanged
    }


def test_update_range_does_not_shrink(state):
    state._state = {
        "spx": {
            "fields": {"v": 1},
            "first_timestamp": 100,
            "last_timestamp": 200,
        }
    }

    state.update_range("spx", first=120, last=180)

    assert state.data["spx"] == {
        "fields": {"v": 1},
        "first_timestamp": 100,  # unchanged
        "last_timestamp": 200,  # unchanged
    }
