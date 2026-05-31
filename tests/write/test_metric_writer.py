# Copyright 2026 Rik Essenius
# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.
# File: tests/write/test_metric_writer.py

from unittest.mock import Mock

import pytest

from finance.write.metric_writer import MetricWriter

# ---------------------------------------------------------------------------
# should_write tests
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "state_entry,timestamp,expected",
    [
        (None, 100, {"ok": True, "reason": "first-time"}),
        ({"fields": {"v": 1}, "last_timestamp": 50}, 100, {"ok": True, "reason": "new"}),
        ({"fields": {"v": 1}, "last_timestamp": 100}, 100, {"ok": False, "reason": "unchanged"}),
        ({"fields": {"v": 1}, "last_timestamp": 200}, 100, {"ok": False, "reason": "older"}),
    ],
)
def test_should_write_cases(state_entry, timestamp, expected):
    state = Mock()
    state.get.return_value = state_entry

    mw = MetricWriter(state)
    result = mw.should_write("spx", timestamp)

    assert result == expected


# ---------------------------------------------------------------------------
# write() tests — MetricWriter should only call state.ingest()
# ---------------------------------------------------------------------------

def test_write_calls_state_ingest_on_new_sample():
    state = Mock()
    state.get.return_value = None
    state.ingest.return_value = {"ok": True, "status": "written"}

    mw = MetricWriter(state)
    result = mw.write("bucket", "spx", {"v": 1}, 100)

    state.ingest.assert_called_once_with({
        "bucket": "bucket",
        "measurement": "spx",
        "fields": {"v": 1},
        "timestamp": 100,
    })

    assert result["ok"] is True


def test_write_skips_unchanged_timestamp():
    state = Mock()
    state.get.return_value = {"fields": {"v": 1}, "last_timestamp": 100}

    mw = MetricWriter(state)
    result = mw.write("bucket", "spx", {"v": 1}, 100)

    state.ingest.assert_not_called()
    assert result["ok"] is False
    assert result["reason"] == "skipped: unchanged sample"


def test_write_skips_older_timestamp():
    state = Mock()
    state.get.return_value = {"fields": {"v": 1}, "last_timestamp": 200}

    mw = MetricWriter(state)
    result = mw.write("bucket", "spx", {"v": 1}, 100)

    state.ingest.assert_not_called()
    assert result["ok"] is False
    assert result["reason"] == "skipped: older sample"


def test_write_passes_through_ingest_result():
    state = Mock()
    state.get.return_value = None
    state.ingest.return_value = {"ok": False, "status": "error", "reason": "boom"}

    mw = MetricWriter(state)
    result = mw.write("bucket", "spx", {"v": 1}, 100)

    assert result["ok"] is False
    assert result["reason"] == "boom"
