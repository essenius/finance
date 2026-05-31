# Copyright 2026 Rik Essenius
# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.
# File: tests/write/test_wal.py

from finance.write.wal import JsonlWAL


def test_wal_enqueue_and_read_all(tmp_path):

    wal_path = tmp_path / "wal.jsonl"
    wal = JsonlWAL(wal_path)

    wal.enqueue({"a": 1})
    wal.enqueue({"b": 2})

    entries = list(wal.read_all())
    assert entries == [{"a": 1}, {"b": 2}]


def test_wal_peek_returns_first_entry(tmp_path):

    wal_path = tmp_path / "wal.jsonl"
    wal = JsonlWAL(wal_path)

    wal.enqueue({"first": 1})
    wal.enqueue({"second": 2})

    assert wal.peek() == {"first": 1}
    # ensure it was NOT removed
    assert list(wal.read_all()) == [{"first": 1}, {"second": 2}]


def test_wal_dequeue_removes_first_entry(tmp_path):

    wal_path = tmp_path / "wal.jsonl"
    wal = JsonlWAL(wal_path)

    wal.enqueue({"first": 1})
    wal.enqueue({"second": 2})

    removed = wal.dequeue()
    assert removed == {"first": 1}

    remaining = list(wal.read_all())
    assert remaining == [{"second": 2}]


def test_wal_empty_behaviour(tmp_path):

    wal_path = tmp_path / "wal.jsonl"
    wal = JsonlWAL(wal_path)

    assert wal.peek() is None
    assert wal.dequeue() is None
    assert list(wal.read_all()) == []


def test_wal_ignores_corrupt_trailing_line(tmp_path):

    wal_path = tmp_path / "wal.jsonl"
    wal = JsonlWAL(wal_path)

    wal.enqueue({"a": 1})
    wal.enqueue({"b": 2})

    # simulate crash: write partial JSON
    with wal_path.open("a") as wal_file:
        wal_file.write('{"incomplete": ')

    entries = list(wal.read_all())
    assert entries == [{"a": 1}, {"b": 2}]


def test_wal_dequeue_skips_corrupt_lines_before_valid_entry(tmp_path):

    wal_path = tmp_path / "wal.jsonl"

    # manually create WAL with corrupt first line
    with wal_path.open("w") as wal_file:
        wal_file.write('{"bad": \n')
        wal_file.write('{"good": 1}\n')
        wal_file.write('{"next": 2}\n')

    wal = JsonlWAL(wal_path)

    removed = wal.dequeue()
    assert removed == {"good": 1}

    remaining = list(wal.read_all())
    assert remaining == [{"next": 2}]


def test_iter_valid_entries_skips_empty_lines(tmp_path):
    wal_path = tmp_path / "wal.jsonl"

    with wal_path.open("w") as wal_file:
        wal_file.write("\n")
        wal_file.write("   \n")
        wal_file.write('{"a": 1}\n')
        wal_file.write("\n")

    wal = JsonlWAL(wal_path)

    entries = list(wal._iter_valid_entries())
    assert entries == [{"a": 1}]
