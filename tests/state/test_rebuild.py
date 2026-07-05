# Copyright 2026 Rik Essenius
# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.
# File: tests/state/test_rebuild.py

from finance.common.model import SeriesPoint, SeriesResult, SeriesState
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

    def read_first(self, series_id):
        return self._first

    def read_last(self, series_id):
        return self._last


class FakeStorage:
    def __init__(self, initial=None):
        self._data = initial or {}

    def load(self):
        return self._data

    def save(self, data):
        self._data = data


def make_backend_result(timestamp, value):
    return SeriesResult.ok_payload("spx", SeriesPoint(series_id=1, time=timestamp, close=value))


def make_backend_fail_result():
    return SeriesResult.fail("spx", "server down")


def make_wal_result(timestamp, value) -> SeriesPoint:
    return SeriesPoint(series_id=1, time=timestamp, close=value)


def make_state(*, wal_entries=None, first=None, last=None, initial_state=None) -> State:
    last = last or make_backend_fail_result()
    first = first or make_backend_fail_result()
    wal = FakeWAL(wal_entries or [])
    store = FakeSeriesStore(first=first, last=last)
    storage = FakeStorage(initial_state)
    return State(store, wal, storage)


def assert_result(result: SeriesState, first: int, last: int):
    assert result.first_time == first
    assert result.last_time == last


# ------
# Tests
# ------


def test_rebuild_wal_only():
    wal_entries = [
        make_wal_result(10, 1),
        make_wal_result(20, 2),
    ]

    state = make_state(wal_entries=wal_entries)

    result = state._rebuild_measurement_state(1)
    assert_result(result, 10, 20)


def test_rebuild_backend_only():
    first = make_backend_result(5, 1)
    last = make_backend_result(15, 2)

    state = make_state(first=first, last=last)

    result = state._rebuild_measurement_state(1)
    assert_result(result, 5, 15)


def test_rebuild_merge_influx_and_wal():
    first = make_backend_result(5, 1)
    last = make_backend_result(15, 2)

    wal_entries = [
        make_wal_result(12, 99),
        make_wal_result(20, 100),
    ]

    state = make_state(wal_entries=wal_entries, first=first, last=last)

    result = state._rebuild_measurement_state(1)
    assert_result(result, 5, 20)


def test_rebuild_empty_everywhere():
    state = make_state()
    assert state._rebuild_measurement_state(1) is None


def test_rebuild_influx_malformed():
    state = make_state(first=make_backend_fail_result(), last=make_backend_fail_result())
    assert state._rebuild_measurement_state(1) is None
