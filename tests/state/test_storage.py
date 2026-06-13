# Copyright 2026 Rik Essenius
# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.
# File: tests/state/test_storage.py

import json

from finance.state.storage import StateStorage


def test_storage_load_missing_file(tmp_path):
    path = tmp_path / "state.json"
    storage = StateStorage(path)

    assert storage.load() == {}


def test_storage_load_valid_dict(tmp_path):
    path = tmp_path / "state.json"
    data = {"spx": {"last_value": 123}}
    path.write_text(json.dumps(data))

    storage = StateStorage(path)
    assert storage.load() == data


def test_storage_load_valid_non_dict(tmp_path):
    path = tmp_path / "state.json"
    path.write_text(json.dumps([1, 2, 3]))  # list, not dict

    storage = StateStorage(path)
    assert storage.load() == {}


def test_storage_load_invalid_json(tmp_path):
    path = tmp_path / "state.json"
    path.write_text("{not valid json}")

    storage = StateStorage(path)
    assert storage.load() == {}


def test_storage_save_atomic_success(tmp_path):
    path = tmp_path / "state.json"
    storage = StateStorage(path)

    state = {"spx": {"last_value": 123}}
    storage.save(state)

    assert path.exists()
    assert json.loads(path.read_text()) == state


def test_storage_save_overwrites_existing(tmp_path):
    path = tmp_path / "state.json"
    path.write_text("OLD DATA")

    storage = StateStorage(path)
    new_state = {"gold": {"last_value": 2000}}

    storage.save(new_state)

    assert json.loads(path.read_text()) == new_state


def test_storage_save_creates_tmp_file_then_replaces(tmp_path):
    """
    Ensure the .tmp file is created and then replaced atomically.
    """
    path = tmp_path / "state.json"
    storage = StateStorage(path)

    state = {"foo": 123}
    storage.save(state)

    # state.json must exist
    assert path.exists()

    # .tmp file should not remain after replace()
    tmp_path = path.with_suffix(".tmp")
    assert not tmp_path.exists()


def test_storage_load_after_save(tmp_path):
    path = tmp_path / "state.json"
    storage = StateStorage(path)

    state = {"spx": {"last_value": 123}}
    storage.save(state)

    loaded = storage.load()
    assert loaded == state
