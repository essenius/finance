# Copyright 2026 Rik Essenius
# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.
# File: tests/write/test_metric_writer.py

from unittest.mock import Mock

import pytest

from finance.write.metric_writer import MetricWriter
from finance.write.wal import JsonlWAL

# ---------------------------------------------------------------------------
# should_write tests
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "entry,timestamp,expected",
    [
        ({}, 100, {"ok": True, "reason": "first-time"}),
        ({"fields": {"value": 123}, "last_timestamp": 50}, 100, {"ok": True, "reason": "new"}),
        ({"fields": {"value": 123}, "last_timestamp": 100}, 100, {"ok": False, "reason": "unchanged"}),
        ({"fields": {"value": 123}, "last_timestamp": 200}, 100, {"ok": False, "reason": "older"}),
    ],
)
def test_should_write_cases(entry, timestamp, expected):
    mw = MetricWriter(Mock(), Mock())
    result = mw.should_write(entry, timestamp)
    assert result == expected


# ---------------------------------------------------------------------------
# write_metric tests (WAL-aware, new return contract)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "initial_state,fields,timestamp,expected_fragment",
    [
        ({}, {"value": 4321}, 100, "wrote value=4321"),
        ({"spx": {"fields": {"value": 4000}, "last_timestamp": 50}}, {"value": 4100}, 100, "wrote value=4100"),
        ({}, {"open": 1, "close": 2}, 100, "open=1"),
    ],
)
def test_write_metric_success(tmp_path, initial_state, fields, timestamp, expected_fragment):
    influx = Mock()
    influx.write.return_value = {"ok": True}

    wal = JsonlWAL(tmp_path / "wal.jsonl")
    mw = MetricWriter(influx, wal)
    state = {"spx": initial_state.get("spx", {})} if initial_state else {}

    result = mw.write_metric("bucket", "spx", fields, timestamp, state)

    assert result["ok"] is True
    assert result["reason"].startswith("wrote")
    assert result["fields"] == fields
    assert result["timestamp"] == timestamp

    assert state["spx"]["fields"] == fields
    assert state["spx"]["last_timestamp"] == timestamp
    assert wal.peek() is None


def test_write_metric_unchanged_timestamp(tmp_path):
    influx = Mock()
    wal = JsonlWAL(tmp_path / "wal.jsonl")
    mw = MetricWriter(influx, wal)

    state = {"spx": {"fields": {"value": 4000}, "last_timestamp": 100}}

    result = mw.write_metric("bucket", "spx", {"value": 4000}, 100, state)

    influx.write.assert_not_called()

    assert result["ok"] is False
    assert result["reason"] == "skipped: unchanged sample"

    assert state["spx"]["fields"] == {"value": 4000}
    assert state["spx"]["last_timestamp"] == 100

    assert wal.peek() is None


def test_write_metric_multi_field(tmp_path):
    influx = Mock()
    influx.write.return_value = {"ok": True}

    wal = JsonlWAL(tmp_path / "wal.jsonl")
    mw = MetricWriter(influx, wal)
    state = {}

    fields = {"open": 1, "close": 2}
    result = mw.write_metric("bucket", "spx", fields, 100, state)

    assert result["ok"] is True
    assert result["fields"] == fields

    assert state["spx"]["fields"] == fields
    assert wal.peek() is None


# ---------------------------------------------------------------------------
# NEW TESTS: WAL behavior
# ---------------------------------------------------------------------------


def test_wal_flushes_multiple_entries(tmp_path):
    influx = Mock()
    influx.write.return_value = {"ok": True}

    wal = JsonlWAL(tmp_path / "wal.jsonl")
    mw = MetricWriter(influx, wal)
    state = {}

    mw.write_metric("bucket", "a", {"value": 1}, 1, state)
    mw.write_metric("bucket", "b", {"value": 2}, 2, state)
    mw.write_metric("bucket", "c", {"value": 3}, 3, state)

    assert influx.write.call_count == 3
    assert wal.peek() is None


@pytest.mark.parametrize(
    "side_effects,expected_remaining_count",
    [
        ([{"ok": True}, {"ok": True}, {"ok": True}], 0),  # all flushed
        ([{"ok": True}, {"ok": False, "error": "down"}], 1),  # stop on failure
    ],
)
def test_wal_flush_behavior(tmp_path, side_effects, expected_remaining_count):
    influx = Mock()
    influx.write.side_effect = side_effects

    wal = JsonlWAL(tmp_path / "wal.jsonl")
    mw = MetricWriter(influx, wal)
    state = {}

    mw.write_metric("bucket", "a", {"value": 1}, 1, state)
    mw.write_metric("bucket", "b", {"value": 2}, 2, state)

    remaining = list(wal.read_all())
    assert len(remaining) == expected_remaining_count


def test_wal_flushes_remaining_after_recovery(tmp_path):
    influx = Mock()

    influx.write.side_effect = [
        {"ok": False, "error": "influx down"},  # first attempt to write A
        {"ok": True},  # second attempt to write A
        {"ok": True},  # then write B
    ]

    wal = JsonlWAL(tmp_path / "wal.jsonl")
    mw = MetricWriter(influx, wal)
    state = {}

    mw.write_metric("bucket", "a", {"value": 1}, 1, state)

    assert wal.peek() is not None

    mw.write_metric("bucket", "b", {"value": 2}, 2, state)

    assert wal.peek() is None


def test_state_updates_even_on_flush_failure(tmp_path):
    influx = Mock()
    influx.write.return_value = {"ok": False, "error": "down"}

    wal = JsonlWAL(tmp_path / "wal.jsonl")
    mw = MetricWriter(influx, wal)
    state = {}

    result = mw.write_metric("bucket", "x", {"value": 10}, 100, state)

    assert result["ok"] is False
    assert state["x"]["fields"] == {"value": 10}
    assert state["x"]["last_timestamp"] == 100

    remaining = list(wal.read_all())
    assert len(remaining) == 1
