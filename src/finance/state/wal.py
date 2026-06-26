# Copyright 2026 Rik Essenius
# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.
# File: src/finance/state/wal.py

import json
from abc import ABC, abstractmethod
from collections.abc import Iterable
from pathlib import Path

from ..common.model import SeriesPoint


# ABC = abstract base class
class WAL(ABC):
    @abstractmethod
    def enqueue(self, point: SeriesPoint) -> None: ...

    @abstractmethod
    def peek(self) -> SeriesPoint | None: ...

    @abstractmethod
    def dequeue(self) -> SeriesPoint | None: ...


class JsonlWAL(WAL):
    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.touch(exist_ok=True)

    def _iter_valid_entries(self) -> Iterable[SeriesPoint]:
        """Yield valid JSON entries from the WAL in order."""
        with self.path.open() as wal_file:
            for line in wal_file:
                stripped = line.strip()
                if not stripped:
                    continue
                try:
                    data = json.loads(stripped)
                    yield SeriesPoint.from_dict(data)
                except Exception:
                    # ignore corrupt lines
                    continue

    def enqueue(self, point: SeriesPoint) -> None:
        """Append a new entry to the WAL."""
        with self.path.open("a") as wal_file:
            wal_file.write(json.dumps(point.to_dict()) + "\n")

    def read_all(self) -> Iterable[SeriesPoint]:
        """Yield all valid entries in order."""
        yield from self._iter_valid_entries()

    def peek(self) -> SeriesPoint | None:
        """Return the oldest valid entry without removing it."""
        for entry in self._iter_valid_entries():
            return entry
        return None

    def dequeue(self) -> SeriesPoint | None:
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
                        data = json.loads(stripped)
                        removed_entry = SeriesPoint.from_dict(data)
                        removed_entry_found = True
                        continue  # don't save this item
                    except Exception:
                        # skip corrupt lines before first valid entry
                        continue

                destination_file.write(line)

        temporary_path.replace(self.path)
        return removed_entry
