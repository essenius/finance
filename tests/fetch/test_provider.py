# Copyright 2026 Rik Essenius
# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.
# File: tests/fetch/test_provider.py

from datetime import datetime, timedelta

import requests

from finance.common.candle_identity import CandleIdentity
from finance.common.time_utils import UTC
from finance.common.types import Success
from finance.fetch.provider import MarketDataProvider


def test_init_defaults(dummy_provider):
    p: MarketDataProvider = dummy_provider()

    assert isinstance(p.session, requests.Session)

    now = p.now()
    assert isinstance(now, datetime)
    assert now.tzinfo == UTC


def test_safe_call_success(dummy_provider):
    p: MarketDataProvider = dummy_provider()

    def good():
        return Success([1, 2, 3])

    result = p._safe_call(good, "context")
    assert result.ok is True
    assert result.payload == [1, 2, 3]


def test_safe_call_exception(dummy_provider):
    p: MarketDataProvider = dummy_provider()

    def bad():
        raise ValueError("kaboom")

    result = p._safe_call(bad, "context")
    assert result.ok is False
    assert "Exception during context" in result.reason
    assert "kaboom" in str(result.error)


# -------------------------
# _safe_get tests
# -------------------------

""" TODO delete
def test_safe_get_ok(dummy_provider):
    p:MarketDataProvider = dummy_provider()
    data = {"a": [{"b": 123}]}

    result = p._safe_get(data, ["a", 0, "b"])
    assert result.ok is True
    assert result.payload == 123


@pytest.mark.parametrize(
    "data, path, expected",
    [
        ({"a": {}}, ["a", "b"], "missing key 'b' at ['a']"),
        ({"a": []}, ["a", 0], "missing index '0' at ['a']"),
        ({"a": 42}, ["a", 0], "cannot index int at ['a']"),
    ],
)
def test_safe_get_errors(dummy_provider, data: Any, path, expected):
    p:MarketDataProvider = dummy_provider()
    result = p._safe_get(data, path)
    assert result.ok is False, "error occurred"
    assert result.reason == expected
"""

# -----------
# Fetch test
# -----------


def test_fetch_not_implemented(dummy_provider, make_series, make_asset_dict, fixed_now):
    assets = make_asset_dict()
    now = CandleIdentity(fixed_now(), False, timedelta(0))
    result = dummy_provider().fetch(make_series(assets["eur_usd"]), assets, start=now, end=now, is_incremental=False)
    assert result.ok is False
    assert result.reason == "fetch not implemented"
