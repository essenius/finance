# Copyright 2026 Rik Essenius
# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.
# File: tests/state/test_rebuild.py

from finance.common.model import TimeseriesResult, TimeseriesWrite
from finance.state.state import State

# --------
# Helpers
# --------


class FakeWAL:
    def __init__(self, entries):
        self._entries = entries

    def read_all(self):
        return self._entries


class FakeSeriesStore:
    def __init__(self, first=None, last=None):
        self._first = first
        self._last = last

    def read_first(self, bucket, measurement):
        return self._first

    def read_last(self, bucket, measurement):
        return self._last


class FakeStorage:
    def __init__(self, initial=None):
        self._data = initial or {}

    def load(self):
        return self._data

    def save(self, data):
        self._data = data


def bucket_for(measurement):
    return "bucket"


def make_influx_result(timestamp, value):
    return TimeseriesResult.ok_payload("spx", TimeseriesWrite("spx", {"v": value}, {}, timestamp, "b"))


def make_influx_fail_result():
    return TimeseriesResult.fail("spx", "server down")


def make_wal_result(timestamp, value):
    return {"measurement": "spx", "timestamp": timestamp, "fields": {"v": value}}


def make_state(*, wal_entries=None, first=None, last=None, initial_state=None):
    last = last or make_influx_fail_result()
    first = first or make_influx_fail_result()
    wal = FakeWAL(wal_entries or [])
    store = FakeSeriesStore(first=first, last=last)
    storage = FakeStorage(initial_state)
    return State(store, wal, storage, bucket_for)


def assert_result(result, first: int, last: int, value: float):
    assert result == {
        "fields": {"v": value},
        "first_timestamp": first,
        "last_timestamp": last,
    }


# ------
# Tests
# ------


def test_rebuild_wal_only():
    wal_entries = [
        make_wal_result(10, 1),
        make_wal_result(20, 2),
    ]

    state = make_state(wal_entries=wal_entries)

    result = state._rebuild_measurement_state("spx")
    assert_result(result, 10, 20, 2)


def test_rebuild_influx_only():
    first = make_influx_result(5, 1)
    last = make_influx_result(15, 2)

    state = make_state(first=first, last=last)

    result = state._rebuild_measurement_state("spx")
    assert_result(result, 5, 15, 2)


def test_rebuild_merge_influx_and_wal():
    first = make_influx_result(5, 1)
    last = make_influx_result(15, 2)

    wal_entries = [
        make_wal_result(12, 99),
        make_wal_result(20, 100),
    ]

    state = make_state(wal_entries=wal_entries, first=first, last=last)

    result = state._rebuild_measurement_state("spx")
    assert_result(result, 5, 20, 100)


def test_rebuild_empty_everywhere():
    state = make_state()
    assert state._rebuild_measurement_state("spx") is None


def test_rebuild_influx_malformed():
    state = make_state(first=make_influx_fail_result(), last=make_influx_fail_result())
    assert state._rebuild_measurement_state("spx") is None
