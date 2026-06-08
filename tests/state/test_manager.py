# Copyright 2026 Rik Essenius
# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.
# File: tests/state/test_manager.py

import json
import tempfile
from pathlib import Path

import pytest

from finance.common.model import TimeseriesResult, TimeseriesWrite
from finance.state.manager import load_state, rebuild_measurement_state, save_state


def test_load_state_missing_file(tmp_path):

    path = tmp_path / "state.json"

    state = load_state(path)

    assert state == {}


def test_load_state_valid_dict(tmp_path):

    path = tmp_path / "state.json"
    data = {"spx": {"last_value": 123}}
    path.write_text(json.dumps(data))

    state = load_state(path)

    assert state == data


def test_load_state_valid_non_dict(tmp_path):

    path = tmp_path / "state.json"
    path.write_text(json.dumps([1, 2, 3]))  # list, not dict

    assert load_state(path) == {}


def test_load_state_invalid_json(tmp_path):

    path = tmp_path / "state.json"
    path.write_text("{not valid json}")

    assert load_state(path) == {}


def test_save_state_atomic_success(tmp_path, monkeypatch):

    # Force NamedTemporaryFile to write into our tmp_path
    monkeypatch.setattr(
        tempfile,
        "NamedTemporaryFile",
        lambda *a, **kw: open(tmp_path / "tempfile.json", "w", encoding="utf-8"),
    )

    path = tmp_path / "state.json"
    state = {"spx": {"last_value": 123}}

    save_state(state, path)

    # File must exist and contain correct JSON
    assert path.exists()
    assert json.loads(path.read_text()) == state


def test_save_state_overwrites_existing(tmp_path, monkeypatch):

    # Fake temp file
    monkeypatch.setattr(
        tempfile,
        "NamedTemporaryFile",
        lambda *a, **kw: open(tmp_path / "tempfile.json", "w", encoding="utf-8"),
    )

    path = tmp_path / "state.json"
    path.write_text("OLD DATA")

    new_state = {"gold": {"last_value": 2000}}

    save_state(new_state, path)

    assert json.loads(path.read_text()) == new_state


def test_save_state_json_failure(tmp_path, monkeypatch):

    # Create a fake temp file path
    temp_file = tmp_path / "tempfile.json"

    # Fake NamedTemporaryFile to return our temp file

    class FakeTemp:
        def __init__(self, name):
            self.name = name

        def write(self, *a, **kw):
            pass

        def flush(self):
            pass

        def close(self):
            pass

    monkeypatch.setattr(tempfile, "NamedTemporaryFile", lambda *a, **kw: FakeTemp(temp_file))

    # Make json.dump fail
    monkeypatch.setattr(json, "dump", lambda *a, **kw: (_ for _ in ()).throw(Exception("boom")))

    # Track unlink calls
    deleted = []

    def fake_unlink(self, missing_ok=False):
        deleted.append(self)

    monkeypatch.setattr(Path, "unlink", fake_unlink)

    with pytest.raises(Exception) as excinfo:
        save_state({"x": 1}, tmp_path / "state.json")

    assert "boom" in str(excinfo.value)

    # Temp file must be deleted
    assert Path(temp_file) in deleted


def test_save_state_unlink_failure(tmp_path, monkeypatch):

    temp_file = tmp_path / "tempfile.json"

    class FakeTemp:
        name = str(temp_file)

        def write(self, *a, **kw):
            pass

        def flush(self):
            pass

        def close(self):
            pass

    monkeypatch.setattr(tempfile, "NamedTemporaryFile", lambda *a, **kw: FakeTemp())

    # json.dump fails
    monkeypatch.setattr(json, "dump", lambda *a, **kw: (_ for _ in ()).throw(Exception("boom")))

    # unlink also fails
    monkeypatch.setattr(Path, "unlink", lambda *a, **kw: (_ for _ in ()).throw(Exception("unlink failed")))

    with pytest.raises(Exception) as excinfo:
        save_state({"x": 1}, tmp_path / "state.json")

    assert "boom" in str(excinfo.value)


def test_load_state_after_atomic_save(tmp_path, monkeypatch):

    monkeypatch.setattr(
        tempfile,
        "NamedTemporaryFile",
        lambda *a, **kw: open(tmp_path / "tempfile.json", "w", encoding="utf-8"),
    )

    path = tmp_path / "state.json"
    state = {"spx": {"last_value": 123}}

    save_state(state, path)

    loaded = load_state(path)
    assert loaded == state


# ---------------------------------------------------------------------------
# rebuild_measurement_state tests
# ---------------------------------------------------------------------------


def test_rebuild_measurement_state_prefers_wal():

    class FakeWAL:
        def read_all(self):
            return [
                TimeseriesWrite("spx", {"value": 100}, {}, 10, "bucket"),
                TimeseriesWrite("spx", {"value": 200}, {}, 20, "bucket"),
            ]

    class FakeInflux:
        def read(self, bucket, measurement):
            raise AssertionError("Influx should not be queried when WAL has entries")

    wal = FakeWAL()
    influx = FakeInflux()

    result = rebuild_measurement_state("bucket", "spx", wal, influx)

    assert result == {"fields": {"value": 200}, "last_timestamp": 20}


def test_rebuild_measurement_state_uses_influx_if_wal_empty():

    class FakeWAL:
        def read_all(self):
            return []

    class FakeInflux:
        def read(self, bucket, measurement):
            assert measurement == "spx"
            return TimeseriesResult.ok_payload("spx", TimeseriesWrite("spx", {"value": 999}, {}, 123, bucket))

    wal = FakeWAL()
    influx = FakeInflux()

    result = rebuild_measurement_state("bucket", "spx", wal, influx)

    assert result == {"fields": {"value": 999}, "last_timestamp": 123}


def test_rebuild_measurement_state_returns_none_if_no_history():

    class FakeWAL:
        def read_all(self):
            return []

    class FakeInflux:
        def read(self, bucket, measurement):
            return TimeseriesResult.fail(measurement, "no data")

    wal = FakeWAL()
    influx = FakeInflux()

    result = rebuild_measurement_state("bucket", "spx", wal, influx)

    assert result is None


def test_rebuild_measurement_state_multiple_wal_entries_newest_wins():

    class FakeWAL:
        def read_all(self):
            return [
                TimeseriesWrite("spx", {"value": 1}, {}, 10, "bucket"),
                TimeseriesWrite("spx", {"value": 2}, {}, 30, "bucket"),
                TimeseriesWrite("spx", {"value": 3}, {}, 20, "bucket"),
            ]

    class FakeInflux:
        def read(self, bucket, measurement):
            raise AssertionError("Should not query Influx when WAL has entries")

    wal = FakeWAL()
    influx = FakeInflux()

    result = rebuild_measurement_state("bucket", "spx", wal, influx)

    assert result == {"fields": {"value": 2}, "last_timestamp": 30}
