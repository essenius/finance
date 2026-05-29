# Copyright 2026 Rik Essenius
# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.
# File: tests/common/test_paths.py

import pytest

from finance.common.paths import get_project_root


def test_get_project_root_valid(monkeypatch, tmp_path):
    """
    If cwd contains config.yaml, get_project_root() must return cwd.
    """
    monkeypatch.chdir(tmp_path)

    # Create config.yaml to mark this as a valid project root
    (tmp_path / "config.yaml").write_text("providers: {}")

    root = get_project_root()
    assert root == tmp_path


def test_get_project_root_invalid(monkeypatch, tmp_path):
    """
    If cwd does NOT contain config.yaml, get_project_root() must raise RuntimeError.
    """
    monkeypatch.chdir(tmp_path)

    # No config.yaml here → invalid project root
    with pytest.raises(RuntimeError):
        get_project_root()


def test_get_project_root_does_not_fallback(monkeypatch, tmp_path):
    """
    Ensure get_project_root() does NOT silently fall back to repo root.
    """
    monkeypatch.chdir(tmp_path)

    # No config.yaml → must raise, not fallback
    with pytest.raises(RuntimeError):
        get_project_root()
