# Copyright 2026 Rik Essenius
# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.
# File: tests/common/test_paths.py

from pathlib import Path

import pytest

import finance.common.paths as paths

# -------------------------------
# get_project_root tests
# -------------------------------


def test_get_project_root_valid(monkeypatch, tmp_path):
    """
    If cwd contains config.yaml, get_project_root() must return cwd.
    """
    monkeypatch.chdir(tmp_path)

    # Create config.yaml to mark this as a valid project root
    (tmp_path / "config.yaml").write_text("providers: {}")

    root = paths.get_project_root()
    assert root == tmp_path


def test_get_project_root_invalid(monkeypatch, tmp_path):
    """
    If cwd does NOT contain config.yaml, get_project_root() must raise RuntimeError.
    """
    monkeypatch.chdir(tmp_path)

    # No config.yaml here → invalid project root
    with pytest.raises(RuntimeError):
        paths.get_project_root()


def test_get_project_root_does_not_fallback(monkeypatch, tmp_path):
    """
    Ensure get_project_root() does NOT silently fall back to repo root.
    """
    monkeypatch.chdir(tmp_path)

    # No config.yaml → must raise, not fallback
    with pytest.raises(RuntimeError):
        paths.get_project_root()


# -------------------------------
# resolve_config_path tests
# -------------------------------


def test_none_uses_project_root_default(tmp_path):
    """If value=None, return project_root/default_filename."""

    result = paths.resolve_config_path(None, "wal.jsonl", tmp_path)

    assert result == tmp_path / "wal.jsonl"
    assert result.is_absolute()


def test_empty_string_uses_project_root_default(tmp_path):
    """If value='', treat it like None."""

    result = paths.resolve_config_path("", "state.json", tmp_path)

    assert result == tmp_path / "state.json"
    assert result.is_absolute()


def test_absolute_path_is_returned_as_is(tmp_path):
    """Absolute paths must be returned unchanged."""

    abs_path = Path("/var/lib/finance/wal.jsonl")
    result = paths.resolve_config_path(str(abs_path), "ignored.json", tmp_path)

    assert result == abs_path
    assert result.is_absolute()


def test_relative_path_is_resolved_against_project_root(tmp_path):
    """Relative paths must be resolved under project root."""

    result = paths.resolve_config_path("data/wal.jsonl", "ignored.json", tmp_path)

    assert result == tmp_path / "data" / "wal.jsonl"
    assert result.is_absolute()


def test_relative_directory_path_appends_default(tmp_path):

    logs_dir = tmp_path / "logs"
    logs_dir.mkdir()  # directory must exist

    result = paths.resolve_config_path("logs", "wal.jsonl", tmp_path)

    assert result == logs_dir / "wal.jsonl"


def test_relative_nonexistent_path_is_treated_as_file(tmp_path):

    result = paths.resolve_config_path("wal", "wal.jsonl", tmp_path)

    # logs/ does NOT exist → treat as file path
    assert result == tmp_path / "wal"
