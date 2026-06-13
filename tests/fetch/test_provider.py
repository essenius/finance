# Copyright 2026 Rik Essenius
# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.
# File: tests/fetch/test_provider.py

from datetime import UTC, datetime
from zoneinfo import ZoneInfo

import pytest
import requests

from finance.common.model import MeasurementResult


def test_init_defaults(dummy_provider):
    p = dummy_provider()

    assert p.api_key is None
    assert p.provider_config.get("timezone") is not None
    assert p.timezone == ZoneInfo("UTC")
    assert isinstance(p.session, requests.Session)

    now = p.now()
    assert isinstance(now, datetime)
    assert now.tzinfo == UTC


def test_safe_call_success(dummy_provider):
    p = dummy_provider()

    def good():
        return MeasurementResult.ok_payload("x", [1, 2, 3])

    result = p._safe_call("ABC", good, "context")
    assert result.ok
    assert result.payload == [1, 2, 3]


def test_safe_call_exception(dummy_provider):
    p = dummy_provider()

    def bad():
        raise ValueError("kaboom")

    result = p._safe_call("ABC", bad, "context")

    assert result.payload is None
    assert "Exception during context" in result.reason
    assert "kaboom" in result.error


# -------------------------
# _safe_get tests
# -------------------------


def test_safe_get_ok(dummy_provider):
    p = dummy_provider()
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
def test_safe_get_errors(dummy_provider, data: any, path, expected):
    p = dummy_provider()
    result = p._safe_get(data, path)
    assert not result.ok
    assert result.payload is None
    assert result.reason == expected


# -----------
# Fetch test
# -----------


def test_fetch_not_implemented(dummy_provider):

    result = dummy_provider().fetch("ABC", {"symbol": "ABC", "fields": ["price"]}, start_timestamp=0, end_timestamp=0)
    assert not result.ok
    assert result.reason == "fetch not implemented"
