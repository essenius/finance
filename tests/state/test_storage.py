# Copyright 2026 Rik Essenius
# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.
# File: tests/state/test_storage.py

import json

from finance.common.model import SeriesState
from finance.state.storage import StateStorage


def test_storage_load_missing_file(tmp_path):
    path = tmp_path / "state.json"
    storage = StateStorage(path)

    assert storage.load() == {}


def test_storage_load_valid_dict(tmp_path, fixed_now):
    now = fixed_now()
    path = tmp_path / "state.json"
    data = {1: {"last_try": now.isoformat(timespec="seconds")}}
    path.write_text(json.dumps(data))

    storage = StateStorage(path)
    state_dict = storage.load()
    assert state_dict[1] == SeriesState(first_time=None, last_time=None, last_try=now)


def test_storage_load_ignore_non_dict(tmp_path):
    path = tmp_path / "state.json"
    path.write_text(json.dumps([1, 2, 3]))  # list, not dict

    storage = StateStorage(path)
    assert storage.load() == {}


def test_storage_load_ignore_non_dict_state(tmp_path):
    path = tmp_path / "state.json"
    path.write_text(json.dumps({1: 1}))  # int, not dict

    storage = StateStorage(path)
    assert storage.load() == {}


def test_storage_load_ignore_non_int_key(tmp_path):
    path = tmp_path / "state.json"
    path.write_text(json.dumps({"a": {}}))  # str, not int

    storage = StateStorage(path)
    assert storage.load() == {}


def test_storage_load_ignore_invalid_json(tmp_path):
    path = tmp_path / "state.json"
    path.write_text("{not valid json}")

    storage = StateStorage(path)
    assert storage.load() == {}


def test_storage_save_atomic_success(tmp_path, fixed_now):
    now = fixed_now()
    path = tmp_path / "state.json"
    storage = StateStorage(path)

    state = {1: SeriesState(last_try=now)}
    storage.save(state)

    assert path.exists()
    result = json.loads(path.read_text())
    assert result["1"] == {"first_time": None, "last_time": None, "last_try": now.isoformat(timespec="seconds")}


def test_storage_save_overwrites_existing(tmp_path, fixed_now):
    now = fixed_now()
    path = tmp_path / "state.json"
    path.write_text("OLD DATA")

    storage = StateStorage(path)
    new_state = {2: SeriesState(last_try=now)}

    storage.save(new_state)

    assert json.loads(path.read_text())["2"] == {"first_time": None, "last_time": None, "last_try": now.isoformat(timespec="seconds")}


def test_storage_save_creates_tmp_file_then_replaces(tmp_path):
    """
    Ensure the .tmp file is created and then replaced atomically.
    """
    path = tmp_path / "state.json"
    storage = StateStorage(path)

    state = {3: SeriesState()}
    storage.save(state)

    # state.json must exist
    assert path.exists()

    # .tmp file should not remain after replace()
    tmp_path = path.with_suffix(".tmp")
    assert not tmp_path.exists()


def test_storage_load_after_save(tmp_path, fixed_now):
    now = fixed_now()
    path = tmp_path / "state.json"
    storage = StateStorage(path)

    state = {3: SeriesState(last_try=now)}
    storage.save(state)

    loaded = storage.load()
    assert loaded == state
