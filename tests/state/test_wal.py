import json
from dataclasses import asdict

from pytest import File

from finance.common.model import TimeseriesWrite
from finance.state.wal import JsonlWAL


def make(measurement="m", field=None, timestamp=0, bucket="b", tags=None):
    return TimeseriesWrite(measurement=measurement, fields=field or {}, timestamp=timestamp, bucket=bucket, tags=tags or {})


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
