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
    def dequeue_multiple(self) -> SeriesPoint | None: ...


class WALCorruptionError(Exception):
    pass


class JsonlWAL(WAL):
    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.touch(exist_ok=True)

    def _parse_line(self, line: str) -> SeriesPoint | None:
        stripped = line.strip()
        if not stripped:
            return None

        try:
            data = json.loads(stripped)
            return SeriesPoint.from_dict(data)
        except Exception as exc:
            raise WALCorruptionError(f"Invalid WAL entry: {stripped}") from exc

    def _iter_parsed_lines(self) -> Iterable[SeriesPoint]:
        with self.path.open() as wal_file:
            for line in wal_file:
                result = self._parse_line(line)
                if result is None:
                    continue
                yield result

    '''
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
    '''

    def enqueue(self, point: SeriesPoint) -> None:
        """Append a new entry to the WAL."""
        with self.path.open("a") as wal_file:
            wal_file.write(json.dumps(point.to_dict()) + "\n")

    def read_all(self) -> Iterable[SeriesPoint]:
        """Yield all valid entries in order."""
        yield from self._iter_parsed_lines()

    def peek(self) -> SeriesPoint | None:
        """Return the oldest valid entry without removing it."""
        for point in self._iter_parsed_lines():
            return point
        return None

    def is_empty(self) -> bool:
        return self.peek() is None

    def dequeue_multiple(self, count: int) -> int:
        """
        Remove the oldest `count` entries.
        Return the number of valid entries actually removed.
        """
        if count == 0:
            return 0
        temporary_path = self.path.with_suffix(".tmp")
        removed = 0

        with self.path.open() as source_file, temporary_path.open("w") as destination_file:
            for line in source_file:
                point = self._parse_line(line)
                if not point:
                    continue

                if removed < count:
                    removed += 1
                    continue

                # After removing `count` valid entries, copy the rest
                destination_file.write(line)

        temporary_path.replace(self.path)
        return removed
