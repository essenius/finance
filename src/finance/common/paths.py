# Copyright 2026 Rik Essenius
# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.
# File: src/finance/common/paths.py

from pathlib import Path


def get_project_root() -> Path:
    """
    The project root is the current working directory,
    but ONLY if it contains config.yaml.

    If not, this is a fatal error — the program must not guess.
    """
    cwd = Path.cwd()
    if (cwd / "config.yaml").exists():
        return cwd

    raise RuntimeError(f"Current working directory {cwd} is not a valid project root (config.yaml not found).")


def resolve_config_path(value: str | None, default_filename: str, project_root: Path) -> Path:
    """
    Resolve a path from config:
    - If value is None or empty: return project_root / default_filename
    - If value is absolute: return it as-is
    - If value is relative: return project_root / value
    """
    if not value:
        return project_root / default_filename

    p = Path(value)

    if p.is_absolute():
        return p

    resolved = project_root / p
    if resolved.is_dir():
        return resolved / default_filename

    return resolved
