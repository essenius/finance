# Copyright 2026 Rik Essenius
# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.
# File: tests/state/test_wal.py

import json
from dataclasses import asdict

from pytest import File

from finance.common.model import TimeseriesWrite
from finance.state.wal import JsonlWAL


def make(measurement="m", field=None, timestamp=0, bucket="b", tags=None):
    return TimeseriesWrite(
        measurement=measurement, fields=field or {}, timestamp=timestamp, bucket=bucket, tags=tags or {}
    )


def write_series(f: File, series: TimeseriesWrite):
    f.write(json.dumps(asdict(series)) + "\n")


def test_wal_enqueue_and_read_all(tmp_path):
    wal_path = tmp_path / "wal.jsonl"
    wal = JsonlWAL(wal_path)

    wal.enqueue(make(field={"a": 1}))
    wal.enqueue(make(field={"b": 2}))

    entries = list(wal.read_all())
    assert entries == [
        make(field={"a": 1}),
        make(field={"b": 2}),
    ]


def test_wal_peek_returns_first_entry(tmp_path):
    wal_path = tmp_path / "wal.jsonl"
    wal = JsonlWAL(wal_path)

    wal.enqueue(make(field={"first": 1}))
    wal.enqueue(make(field={"second": 2}))

    assert wal.peek() == make(field={"first": 1})
    assert list(wal.read_all()) == [
        make(field={"first": 1}),
        make(field={"second": 2}),
    ]


def test_wal_dequeue_removes_first_entry(tmp_path):
    wal_path = tmp_path / "wal.jsonl"
    wal = JsonlWAL(wal_path)

    wal.enqueue(make(field={"first": 1}))
    wal.enqueue(make(field={"second": 2}))

    removed = wal.dequeue()
    assert removed == make(field={"first": 1})

    remaining = list(wal.read_all())
    assert remaining == [make(field={"second": 2})]


def test_wal_empty_behaviour(tmp_path):
    wal_path = tmp_path / "wal.jsonl"
    wal = JsonlWAL(wal_path)

    assert wal.peek() is None
    assert wal.dequeue() is None
    assert list(wal.read_all()) == []


def test_wal_ignores_corrupt_trailing_line(tmp_path):
    wal_path = tmp_path / "wal.jsonl"
    wal = JsonlWAL(wal_path)

    wal.enqueue(make(field={"a": 1}))
    wal.enqueue(make(field={"b": 2}))

    with wal_path.open("a") as wal_file:
        wal_file.write('{"incomplete": ')

    assert list(wal.read_all()) == [
        make(field={"a": 1}),
        make(field={"b": 2}),
    ]


def test_wal_dequeue_skips_corrupt_lines_before_valid_entry(tmp_path):
    wal_path = tmp_path / "wal.jsonl"

    good = make(field={"good": 1})
    next = make(field={"next": 2})
    with wal_path.open("w") as wal_file:
        wal_file.write('{"bad": \n')
        write_series(wal_file, good)
        write_series(wal_file, next)

    wal = JsonlWAL(wal_path)

    removed = wal.dequeue()
    assert removed == good

    remaining = list(wal.read_all())
    assert remaining == [next]


def test_iter_valid_entries_skips_empty_lines(tmp_path):
    wal_path = tmp_path / "wal.jsonl"

    entry = make(field={"a": 1})
    with wal_path.open("w") as wal_file:
        wal_file.write("\n")
        wal_file.write("   \n")
        write_series(wal_file, entry)
        wal_file.write("\n")

    wal = JsonlWAL(wal_path)

    assert list(wal._iter_valid_entries()) == [entry]


def test_wal_append_is_atomic(tmp_path):
    wal_path = tmp_path / "wal.jsonl"
    wal = JsonlWAL(wal_path)

    wal.enqueue(make(field={"a": 1}))

    with wal_path.open("a") as f:
        f.write('{"b": ')  # incomplete JSON

    assert list(wal.read_all()) == [make(field={"a": 1})]


def test_wal_skips_multiple_corrupt_middle_lines(tmp_path):
    wal_path = tmp_path / "wal.jsonl"

    first = make(field={"a": 1})
    second = make(field={"b": 2})
    with wal_path.open("w") as f:
        write_series(f, first)
        f.write('{"bad": \n')
        f.write('{"also_bad": \n')
        write_series(f, second)

    wal = JsonlWAL(wal_path)
    assert list(wal.read_all()) == [
        make(field={"a": 1}),
        make(field={"b": 2}),
    ]


def test_wal_creates_file_if_missing(tmp_path):
    wal_path = tmp_path / "wal.jsonl"
    wal = JsonlWAL(wal_path)

    wal.enqueue(make(field={"x": 1}))

    assert wal_path.exists()
    assert list(wal.read_all()) == [make(field={"x": 1})]


# ------------------
# read_batch
# ------------------


def test_wal_read_batch_empty(tmp_path):
    wal_path = tmp_path / "wal.jsonl"
    wal = JsonlWAL(wal_path)

    assert wal.read_batch(5) == []


def test_wal_read_batch_fewer_than_n(tmp_path):
    wal_path = tmp_path / "wal.jsonl"
    wal = JsonlWAL(wal_path)

    first = make(field={"a": 1})
    second = make(field={"b": 2})

    wal.enqueue(first)
    wal.enqueue(second)

    assert wal.read_batch(5) == [first, second]


def test_wal_read_batch_exact_n(tmp_path):
    wal_path = tmp_path / "wal.jsonl"
    wal = JsonlWAL(wal_path)

    entries = [make(field={"v": i}) for i in range(3)]
    for e in entries:
        wal.enqueue(e)

    assert wal.read_batch(3) == entries


def test_wal_read_batch_more_than_n(tmp_path):
    wal_path = tmp_path / "wal.jsonl"
    wal = JsonlWAL(wal_path)

    entries = [make(field={"v": i}) for i in range(5)]
    for e in entries:
        wal.enqueue(e)

    assert wal.read_batch(3) == entries[:3]


def test_wal_read_batch_skips_corrupt_lines(tmp_path):
    wal_path = tmp_path / "wal.jsonl"

    good1 = make(field={"a": 1})
    good2 = make(field={"b": 2})

    with wal_path.open("w") as f:
        f.write('{"bad": \n')
        write_series(f, good1)
        f.write('{"also_bad": \n')
        write_series(f, good2)

    wal = JsonlWAL(wal_path)

    assert wal.read_batch(5) == [good1, good2]


# ---------------------
# remove_indices()
# ---------------------


def test_wal_remove_indices_remove_none(tmp_path):
    wal_path = tmp_path / "wal.jsonl"
    wal = JsonlWAL(wal_path)

    entries = [make(field={"v": i}) for i in range(3)]
    for e in entries:
        wal.enqueue(e)

    wal.remove_indices([])

    assert list(wal.read_all()) == entries


def test_wal_remove_indices_remove_all(tmp_path):
    wal_path = tmp_path / "wal.jsonl"
    wal = JsonlWAL(wal_path)

    entries = [make(field={"v": i}) for i in range(3)]
    for e in entries:
        wal.enqueue(e)

    wal.remove_indices([0, 1, 2])

    assert list(wal.read_all()) == []


def test_wal_remove_indices_remove_some(tmp_path):
    wal_path = tmp_path / "wal.jsonl"
    wal = JsonlWAL(wal_path)

    e0 = make(field={"v": 0})
    e1 = make(field={"v": 1})
    e2 = make(field={"v": 2})
    e3 = make(field={"v": 3})

    for e in [e0, e1, e2, e3]:
        wal.enqueue(e)

    wal.remove_indices([1, 3])  # remove e1 and e3

    assert list(wal.read_all()) == [e0, e2]


def test_wal_remove_indices_preserves_order(tmp_path):
    wal_path = tmp_path / "wal.jsonl"
    wal = JsonlWAL(wal_path)

    entries = [make(field={"v": i}) for i in range(5)]
    for e in entries:
        wal.enqueue(e)

    wal.remove_indices([0, 2])

    assert list(wal.read_all()) == [entries[1], entries[3], entries[4]]


def test_wal_remove_indices_skips_corrupt_lines(tmp_path):
    wal_path = tmp_path / "wal.jsonl"

    good1 = make(field={"a": 1})
    good2 = make(field={"b": 2})
    good3 = make(field={"c": 3})

    with wal_path.open("w") as f:
        f.write('{"bad": \n')  # corrupt
        write_series(f, good1)  # index 0
        f.write('{"also_bad": \n')  # corrupt
        write_series(f, good2)  # index 1
        write_series(f, good3)  # index 2

    wal = JsonlWAL(wal_path)

    wal.remove_indices([1])  # remove good2

    assert list(wal.read_all()) == [good1, good3]


def test_wal_remove_indices_drops_empty_and_corrupt_lines(tmp_path):
    wal_path = tmp_path / "wal.jsonl"

    e0 = make(field={"v": 0})
    e1 = make(field={"v": 1})

    with wal_path.open("w") as f:
        f.write("\n")  # empty
        f.write('{"bad": \n')  # corrupt
        write_series(f, e0)  # index 0
        f.write("\n")  # empty
        write_series(f, e1)  # index 1

    wal = JsonlWAL(wal_path)

    wal.remove_indices([0])  # remove e0

    assert list(wal.read_all()) == [e1]


# roundtrip


def test_wal_roundtrip_preserves_all_fields(tmp_path):
    wal_path = tmp_path / "wal.jsonl"
    wal = JsonlWAL(wal_path)

    entry = make(
        measurement="m",
        field={"a": 1, "b": 2},
        timestamp=123456,
        bucket="bucket",
        tags={"host": "pi", "sensor": "temp"},
    )

    wal.enqueue(entry)
    read_back = list(wal.read_all())[0]

    assert read_back == entry
