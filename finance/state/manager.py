# Copyright 2026 Rik Essenius
# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.
# File: finance/state/manager.py

import json
import shutil
import tempfile
from pathlib import Path

from finance.common.paths import get_project_root

DEFAULT_STATE_FILE = "state.json"


def load_state(path: Path | None = None) -> dict:
    """
    Load state.json from the project root unless an explicit path is provided.
    """
    if path is None:
        root = get_project_root()
        path = root / DEFAULT_STATE_FILE

    if not path.exists():
        return {}

    try:
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, dict):
                return data
    except Exception:
        pass  # corrupted or unreadable

    return {}


def save_state(state: dict, path: Path | None = None):
    """
    Save state atomically to avoid corruption.
    """
    if path is None:
        root = get_project_root()
        path = root / DEFAULT_STATE_FILE

    tmp = tempfile.NamedTemporaryFile("w", delete=False, encoding="utf-8")
    try:
        json.dump(state, tmp, indent=2)
        tmp.flush()
        tmp.close()
        shutil.move(tmp.name, path)
    except Exception:
        try:
            Path(tmp.name).unlink(missing_ok=True)
        except Exception:
            pass
        raise
