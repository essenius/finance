# Copyright 2026 Rik Essenius
# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.
# File: finance/common/paths.py

from pathlib import Path


def get_project_root() -> Path:
    """
    The project root is ALWAYS the current working directory,
    but ONLY if it contains config.ini.

    If not, this is a fatal error — the program must not guess.
    """
    cwd = Path.cwd()
    if (cwd / "config.yaml").exists():
        return cwd

    raise RuntimeError(f"Current working directory {cwd} is not a valid project root (config.ini not found).")
