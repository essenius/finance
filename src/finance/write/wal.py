# Copyright 2026 Rik Essenius
# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.
# File: src/finance/write/wal.py

import json
from pathlib import Path


class JsonlWAL:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.touch(exist_ok=True)

    def _iter_valid_entries(self):
        """Yield valid JSON entries from the WAL in order."""
        with self.path.open() as wal_file:
            for line in wal_file:
                stripped = line.strip()
                if not stripped:
                    continue
                try:
                    yield json.loads(stripped)
                except json.JSONDecodeError:
                    # ignore corrupt lines
                    continue

    def enqueue(self, entry):
        """Append a new entry to the WAL."""
        with self.path.open("a") as wal_file:
            wal_file.write(json.dumps(entry) + "\n")

    def read_all(self):
        """Yield all valid entries in order."""
        yield from self._iter_valid_entries()

    def peek(self):
        """Return the oldest valid entry without removing it."""
        for entry in self._iter_valid_entries():
            return entry
        return None

    def dequeue(self):
        """
        Remove and return the oldest valid entry.
        Returns None if no valid entries exist.
        """
        temporary_path = self.path.with_suffix(".tmp")

        removed_entry = None
        removed_entry_found = False

        with self.path.open() as source_file, temporary_path.open("w") as destination_file:
            for line in source_file:
                stripped = line.strip()

                if not removed_entry_found:
                    try:
                        removed_entry = json.loads(stripped)
                        removed_entry_found = True
                        continue  # skip writing this line
                    except json.JSONDecodeError:
                        # skip corrupt lines before first valid entry
                        continue

                destination_file.write(line)

        temporary_path.replace(self.path)
        return removed_entry
