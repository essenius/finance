# Copyright 2026 Rik Essenius
# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.
# File: tests/fetch/test_provider.py

from datetime import UTC, datetime

import pytest

from finance.common.model import FetchPoint, FetchResult, MeasurementResult
from finance.fetch.provider import MarketDataProvider


class DummyProvider(MarketDataProvider):
    def fetch(self, asset: str, last_timestamp: int) -> FetchResult:
        return FetchResult.ok_payload(
            measurement=asset, payload=[FetchPoint(timestamp=last_timestamp, fields={"price": 10})]
        )


def test_init_defaults():
    p = DummyProvider()

    # config defaults to empty dict
    assert p.config == {}

    # now_provider defaults to a callable returning UTC datetime
    now = p.now()
    assert isinstance(now, datetime)
    assert now.tzinfo == UTC


def test_safe_call_success():
    p = DummyProvider()

    def good():
        return MeasurementResult.ok_payload("x", [1, 2, 3])

    result = p._safe_call("ABC", good, "context")
    assert result.ok
    assert result.payload == [1, 2, 3]


def test_safe_call_exception():
    p = DummyProvider()

    def bad():
        raise ValueError("kaboom")

    result = p._safe_call("ABC", bad, "context")

    assert result.payload is None
    assert "Exception during context" in result.reason
    assert "kaboom" in result.error


# -------------------------
# _safe_get tests
# -------------------------


def test_safe_get_ok():
    p = DummyProvider()
    data = {"a": [{"b": 123}]}

    result = p._safe_get(data, ["a", 0, "b"])
    assert result.ok
    assert result.payload == 123
    assert result.reason is None
    assert result.error is None


@pytest.mark.parametrize(
    "data, path, expected",
    [
        ({"a": {}}, ["a", "b"], "missing key 'b' at ['a']"),
        ({"a": []}, ["a", 0], "missing index [0] at ['a']"),
        ({"a": 42}, ["a", 0], "cannot index with [0] at ['a']"),
    ],
)
def test_safe_get_errors(data: any, path, expected):
    p = DummyProvider()
    result = p._safe_get(data, path)
    assert not result.ok
    assert result.payload is None
    assert result.reason == expected


def test_fetch_not_implemented():

    result = MarketDataProvider().fetch("ABC", {"symbol": "ABC", "fields": ["price"]}, last_timestamp=None)
    assert not result.ok
    assert result.reason == "fetch not implemented"
