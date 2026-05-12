# Copyright 2026 Rik Essenius
# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.
# File: tools/add_license/__init__.py

from datetime import datetime
from pathlib import Path

from .file_processor import FileProcessor
from .main import main as _main

# These exist only so tests can monkeypatch them
PROJECT_ROOT = Path(__file__).resolve().parents[2]
CURRENT_YEAR = datetime.now().year

def add_license_to_file(path: Path):
    """Compatibility wrapper for tests."""
    from . import CURRENT_YEAR, PROJECT_ROOT
    processor = FileProcessor(path, PROJECT_ROOT, CURRENT_YEAR)
    processor.process()


def main():
    """main entry point for command line usage."""
    from . import CURRENT_YEAR, PROJECT_ROOT
    _main(PROJECT_ROOT, CURRENT_YEAR)
