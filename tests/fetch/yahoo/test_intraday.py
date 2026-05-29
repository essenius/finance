# Copyright 2026 Rik Essenius
# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.
# File: tests/fetch/yahoo/test_intraday.py


# ----------------------------------------------------------------------
# Intraday tests (using provider fixture from conftest)
# ----------------------------------------------------------------------

from datetime import timedelta

import pytest

INTRADAY_CASES = [
    # _fetch returns None → []
    (
        lambda provider: None,  # _fetch
        lambda data, symbol: [],  # _extract_candles
        [],  # expected
    ),
    # candles returned → use candles
    (
        lambda provider: {"chart": {"result": [{}]}},
        lambda data, symbol: [
            {"timestamp": 100, "fields": {"close": 1.1}},
            {"timestamp": 200, "fields": {"close": 1.2}},
        ],
        [
            {"timestamp": 100, "fields": {"close": 1.1}},
            {"timestamp": 200, "fields": {"close": 1.2}},
        ],
    ),
    # no candles → fallback to metadata
    (
        lambda provider: {
            "meta": {
                "regularMarketTime": 1000,
                "regularMarketPrice": 1.234,
            }
        },
        lambda data, symbol: [],
        [
            {"timestamp": 1000, "fields": {"close": 1.234}},
        ],
    ),
]


@pytest.mark.parametrize("fetch_fn, candle_fn, expected", INTRADAY_CASES)
def test_intraday_basic(provider, monkeypatch, fetch_fn, candle_fn, expected):
    monkeypatch.setattr(provider, "_fetch", lambda *a, **kw: fetch_fn(provider))
    monkeypatch.setattr(provider, "_extract_candles", candle_fn)

    result = provider._fetch_intraday("EURUSD=X", ["close"], last_timestamp=None)
    assert result == expected


def test_intraday_range_initial_load(provider, monkeypatch):
    provider.config["intraday_history_limit"] = "5d"

    # First call: ignore result, just warm up
    monkeypatch.setattr(provider, "_fetch", lambda *a, **kw: {"chart": {"result": [{}]}})
    monkeypatch.setattr(provider, "_extract_candles", lambda data, symbol: [])

    provider._fetch_intraday("EURUSD=X", ["close"], last_timestamp=None)

    # Capture the actual range passed
    captured = {}

    def fake_fetch(symbol, interval_str, range_str):
        captured["range"] = range_str
        return {"chart": {"result": [{}]}}

    monkeypatch.setattr(provider, "_fetch", fake_fetch)
    provider._fetch_intraday("EURUSD=X", ["close"], last_timestamp=None)

    assert captured["range"] == "5d"


def test_intraday_range_incremental(provider, monkeypatch):
    provider.config["intraday_history_limit"] = "5d"

    # last_timestamp within 60 seconds → incremental → "1m"
    recent_ts = int(provider.now().timestamp()) - 60

    captured = {}

    def fake_fetch(symbol, interval_str, range_str):
        captured["range"] = range_str
        return {"chart": {"result": [{}]}}

    monkeypatch.setattr(provider, "_fetch", fake_fetch)
    monkeypatch.setattr(provider, "_extract_candles", lambda data, symbol: [])

    provider._fetch_intraday("EURUSD=X", ["close"], last_timestamp=recent_ts)

    assert captured["range"] == "1m"


def test_intraday_range_exceeds_history_limit(provider, monkeypatch):
    # Configure a small history limit so we can exceed it easily
    provider.config["intraday_history_limit"] = "5d"

    # last_timestamp is 10 days old → older than 5d → must use history limit
    old_ts = int((provider.now() - timedelta(days=10)).timestamp())

    captured = {}

    def fake_fetch(symbol, interval_str, range_str):
        captured["range"] = range_str
        return {"chart": {"result": [{}]}}

    monkeypatch.setattr(provider, "_fetch", fake_fetch)
    monkeypatch.setattr(provider, "_extract_candles", lambda data, symbol: [])

    provider._fetch_intraday("EURUSD=X", ["close"], last_timestamp=old_ts)

    assert captured["range"] == "5d"
