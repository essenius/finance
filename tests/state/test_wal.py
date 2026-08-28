# Copyright 2026 Rik Essenius
# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.
# File: tests/state/test_wal.py

import json
from datetime import datetime
from io import TextIOWrapper
from pathlib import Path

import pytest

from finance.common.model import SeriesPoint
from finance.common.time_utils import UTC
from finance.state.wal import JsonlWAL, WALCorruptionError
from tests.support.types import Factory


def make(value: float, *, series_id: int = 1, time: datetime = datetime(2026, 1, 1, tzinfo=UTC)) -> SeriesPoint:
    return SeriesPoint(series_id=series_id, time=time, close=value)


def write_series(f: TextIOWrapper, series: SeriesPoint):
    f.write(json.dumps(series.to_dict()) + "\n")


def test_wal_enqueue_and_read_all(tmp_path: Path):
    wal_path = tmp_path / "wal.jsonl"
    wal = JsonlWAL(wal_path)

    wal.enqueue(make(value=1))
    wal.enqueue(make(value=2))

    entries = list(wal.read_all())
    assert entries == [
        make(value=1),
        make(value=2),
    ]


def test_wal_peek_returns_first_entry(tmp_path: Path):
    wal_path = tmp_path / "wal.jsonl"
    wal = JsonlWAL(wal_path)

    wal.enqueue(make(value=1))
    wal.enqueue(make(value=2))

    assert wal.peek() == make(value=1)
    assert list(wal.read_all()) == [
        make(value=1),
        make(value=2),
    ]


def test_wal_dequeue_removes_first_entry(tmp_path: Path):
    wal_path = tmp_path / "wal.jsonl"
    wal = JsonlWAL(wal_path)

    wal.enqueue(make(value=1))
    wal.enqueue(make(value=2))

    removed = wal.dequeue_multiple(1)
    assert removed == 1

    remaining = list(wal.read_all())
    assert remaining == [make(value=2)]
    assert not wal.is_empty()


def test_wal_empty_behaviour(tmp_path: Path):
    wal_path = tmp_path / "wal.jsonl"

    # add empty line to see if it's ignored
    with wal_path.open("a") as wal_file:
        wal_file.write("\n")
    wal = JsonlWAL(wal_path)

    assert wal.is_empty()
    assert wal.peek() is None
    assert wal.dequeue_multiple(1) == 0
    assert list(wal.read_all()) == []
    assert wal.dequeue_multiple(0) == 0


def test_wal_dequeue_corrupt_lines(tmp_path: Path):
    wal_path = tmp_path / "wal.jsonl"

    good = make(value=1)
    next = make(value=2)
    with wal_path.open("w") as wal_file:
        wal_file.write('{"bad": \n')
        write_series(wal_file, good)
        write_series(wal_file, next)

    wal = JsonlWAL(wal_path)
    with pytest.raises(WALCorruptionError) as wce:
        wal.dequeue_multiple(1)
    assert 'Invalid WAL entry: {"bad":' in str(wce.value)


def test_iter_entries_skips_empty_lines(tmp_path: Path):
    wal_path = tmp_path / "wal.jsonl"

    entry = make(value=1)
    with wal_path.open("w") as wal_file:
        wal_file.write("\n")
        wal_file.write("   \n")
        write_series(wal_file, entry)
        wal_file.write("\n")

    wal = JsonlWAL(wal_path)

    result = list(wal._iter_parsed_lines())
    assert result == [entry]


def test_wal_append_is_atomic(tmp_path: Path):
    wal_path = tmp_path / "wal.jsonl"
    wal = JsonlWAL(wal_path)

    wal.enqueue(make(value=1))

    assert list(wal.read_all()) == [make(value=1)]


def test_wal_creates_file_if_missing(tmp_path: Path):
    wal_path = tmp_path / "wal.jsonl"
    wal = JsonlWAL(wal_path)

    wal.enqueue(make(value=1))

    assert wal_path.exists()
    assert list(wal.read_all()) == [make(value=1)]


# ---------------
# roundtrip
# ---------------


def test_wal_roundtrip_preserves_all_fields(fixed_now: Factory[datetime], tmp_path: Path):
    wal_path = tmp_path / "wal.jsonl"
    wal = JsonlWAL(wal_path)

    entry = make(
        series_id=1,
        value=2,
        time=fixed_now(),
    )

    wal.enqueue(entry)
    read_back = list(wal.read_all())[0]

    assert read_back == entry
