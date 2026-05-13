# Copyright 2026 Rik Essenius
# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.
# File: tools/add_license/main.py

import os
from pathlib import Path

from .file_processor import FileProcessor

SKIP_DIRS = {
    ".git",
    ".venv",
    "venv",
    "env",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    "build",
    "dist",
    "node_modules",
}


def main(project_root: Path, current_year: int):
    for root, dirs, files in os.walk(project_root):
        # Prevent descending into hidden or unwanted directories
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS and not d.startswith(".")]

        for file in files:
            if file.endswith(".py"):
                path = Path(root) / file
                FileProcessor(path, project_root, current_year).process()
