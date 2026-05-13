# Copyright 2026 Rik Essenius
# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.
# File: tests/test_write_controller.py

from unittest.mock import Mock

from finance.write.controller import should_write, write_metric


def test_should_write_first_time():
    entry = {}
    ok, reason = should_write(entry, ts=100)
    assert ok is True
    assert reason == "first-time write"


def test_should_write_new_timestamp():
    entry = {"last_value": 123, "last_timestamp": 50}
    ok, reason = should_write(entry, ts=100)
    assert ok is True
    assert reason == "new sample"


def test_should_write_unchanged_timestamp():
    entry = {"last_value": 123, "last_timestamp": 100}
    ok, reason = should_write(entry, ts=100)
    assert ok is False
    assert reason == "unchanged"


def test_write_metric_first_time():
    influx = Mock()
    state = {}

    msg = write_metric("spx", 4321, 100, state, influx)

    influx.write.assert_called_once_with("spx", {"value": 4321}, 100)

    assert state["spx"]["last_value"] == 4321
    assert state["spx"]["last_timestamp"] == 100

    assert msg == "spx: wrote (4321/100)"


def test_write_metric_new_timestamp():
    influx = Mock()
    state = {"spx": {"last_value": 4000, "last_timestamp": 50}}

    msg = write_metric("spx", 4100, 100, state, influx)

    influx.write.assert_called_once_with("spx", {"value": 4100}, 100)

    assert state["spx"]["last_value"] == 4100
    assert state["spx"]["last_timestamp"] == 100

    assert msg == "spx: wrote (4100/100)"


def test_write_metric_unchanged_timestamp():
    influx = Mock()
    state = {"spx": {"last_value": 4000, "last_timestamp": 100}}

    msg = write_metric("spx", 4000, 100, state, influx)

    influx.write.assert_not_called()

    # State must NOT change
    assert state["spx"]["last_value"] == 4000
    assert state["spx"]["last_timestamp"] == 100

    assert msg == "spx: unchanged"


def test_write_metric_influx_failure_does_not_crash():
    influx = Mock()
    influx.write.side_effect = Exception("boom")

    state = {}

    msg = write_metric("spx", 123, 100, state, influx)

    # Write was attempted
    influx.write.assert_called_once_with("spx", {"value": 123}, 100)

    # Even if write fails, state is updated
    assert state["spx"]["last_value"] == 123
    assert state["spx"]["last_timestamp"] == 100

    # Message still reports write
    assert msg == "spx: Influx could not write (123/100)"
