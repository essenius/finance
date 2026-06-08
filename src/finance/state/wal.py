# Copyright 2026 Rik Essenius
# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.
# File: src/finance/state/wal.py

import json
from collections.abc import Iterable
from dataclasses import asdict
from pathlib import Path

from ..common.model import TimeseriesWrite


class JsonlWAL:
    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.touch(exist_ok=True)

    def _iter_valid_entries(self) -> Iterable[TimeseriesWrite]:
        """Yield valid JSON entries from the WAL in order."""
        with self.path.open() as wal_file:
            for line in wal_file:
                stripped = line.strip()
                if not stripped:
                    continue
                try:
                    yield TimeseriesWrite(**json.loads(stripped))
                except json.JSONDecodeError:
                    # ignore corrupt lines
                    continue

    def enqueue(self, entry: TimeseriesWrite) -> None:
        """Append a new entry to the WAL."""
        with self.path.open("a") as wal_file:
            wal_file.write(json.dumps(asdict(entry)) + "\n")

    def read_all(self) -> Iterable[TimeseriesWrite]:
        """Yield all valid entries in order."""
        yield from self._iter_valid_entries()

    def peek(self) -> TimeseriesWrite | None:
        """Return the oldest valid entry without removing it."""
        for entry in self._iter_valid_entries():
            return entry
        return None

    def dequeue(self) -> TimeseriesWrite | None:
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
                        removed_entry = TimeseriesWrite(**json.loads(stripped))
                        removed_entry_found = True
                        continue  # don't save this item
                    except json.JSONDecodeError:
                        # skip corrupt lines before first valid entry
                        continue

                destination_file.write(line)

        temporary_path.replace(self.path)
        return removed_entry
