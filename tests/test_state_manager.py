# Copyright 2026 Rik Essenius
# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.
# File: tests/test_state_manager.py

from pathlib import Path


def test_load_state_missing_file(tmp_path):
    from finance.state.manager import load_state

    path = tmp_path / "state.json"

    state = load_state(path)

    assert state == {}


def test_load_state_valid_dict(tmp_path):
    import json

    from finance.state.manager import load_state

    path = tmp_path / "state.json"
    data = {"spx": {"last_value": 123}}
    path.write_text(json.dumps(data))

    state = load_state(path)

    assert state == data


def test_load_state_valid_non_dict(tmp_path):
    import json

    from finance.state.manager import load_state

    path = tmp_path / "state.json"
    path.write_text(json.dumps([1, 2, 3]))  # list, not dict

    assert load_state(path) == {}


def test_load_state_invalid_json(tmp_path):
    from finance.state.manager import load_state

    path = tmp_path / "state.json"
    path.write_text("{not valid json}")

    assert load_state(path) == {}


def test_save_state_atomic_success(tmp_path, monkeypatch):
    import json
    import tempfile

    from finance.state.manager import save_state

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
    import json
    import tempfile

    from finance.state.manager import save_state

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
    import json
    import tempfile
    from pathlib import Path

    import pytest

    from finance.state.manager import save_state

    # Create a fake temp file path
    temp_file = tmp_path / "tempfile.json"

    # Fake NamedTemporaryFile to return our temp file
    class FakeTemp:
        name = str(temp_file)

        def write(self, *a, **kw):
            pass

        def flush(self):
            pass

        def close(self):
            pass

    monkeypatch.setattr(tempfile, "NamedTemporaryFile", lambda *a, **kw: FakeTemp())

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
    import json
    import tempfile

    import pytest

    from finance.state.manager import save_state

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
    import tempfile

    from finance.state.manager import load_state, save_state

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
