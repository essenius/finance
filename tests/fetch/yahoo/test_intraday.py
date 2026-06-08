# Copyright 2026 Rik Essenius
# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.
# File: tests/fetch/yahoo/test_intraday.py


# ----------------------------------------------------------------------
# Intraday tests (using provider fixture from conftest)
# ----------------------------------------------------------------------

from datetime import timedelta

import pytest

from finance.common.model import FetchPoint, FetchResult

INTRADAY_CASES = [
    # 1) _fetch fails → return FetchResult.fail
    dict(
        fetch_result=FetchResult.fail("eurusd", "boom"),
        candle_result=None,  # won't be used
        expected_ok=False,
        expected_payload=None,
    ),

    # 2) candles exist → convert to FetchPoints
    dict(
        fetch_result=FetchResult.ok_payload("eurusd", payload={"chart": {"result": [{}]}}),
        candle_result=FetchResult.ok_payload(
            "eurusd",
            payload=[
                FetchPoint(timestamp=100, fields={ "open":0, "high": 0, "low": 0, "close": 1.1, "volume": 0}),
                FetchPoint(timestamp=200, fields={ "open":0, "high": 0, "low": 0, "close": 1.2, "volume": 0}),
            ],
        ),
        expected_ok=True,
        expected_payload=[
            FetchPoint(timestamp=100, fields={"price": 1.1}),
            FetchPoint(timestamp=200, fields={"price": 1.2}),
        ],
    ),

    # 3) no candles → fallback to metadata
    dict(
        fetch_result=FetchResult.ok_payload(
            "eurusd",
            payload={"meta": {"regularMarketTime": 1000, "regularMarketPrice": 1.234}},
        ),
        candle_result=FetchResult.ok_payload("eurusd", payload=[]),
        expected_ok=True,
        expected_payload=[
            FetchPoint(timestamp=1000, fields={"price": 1.234}),
        ],
    ),
]

@pytest.mark.parametrize("case", INTRADAY_CASES)
def test_intraday_basic(provider, monkeypatch, case):
    # Patch _fetch to return the pre-baked FetchResult
    monkeypatch.setattr(provider, "_fetch", lambda *a, **kw: case["fetch_result"])

    # Patch _extract_candles to return the pre-baked candle list
    if case["candle_result"] is not None:
        monkeypatch.setattr(provider, "_extract_candles", lambda results, fields=None, today=None: case["candle_result"])

    result = provider._fetch_intraday(name="eurusd", symbol="EURUSD=X", last_timestamp=None)

    assert result.ok == case["expected_ok"]
    assert result.payload == case["expected_payload"]



def test_intraday_range_initial_load(provider, monkeypatch):
    provider.config["intraday_history_limit"] = "5d"

    # First call: ignore result, just warm up
    monkeypatch.setattr(provider, "_fetch", lambda *a, **kw: FetchResult.ok_payload("eurusd", {"chart": {"result": [{}]}}))
    monkeypatch.setattr(provider, "_extract_candles", lambda results, fields=None, today=None: FetchResult.ok_payload("eurusd", []))

    provider._fetch_intraday("eurusd", "EURUSD=X", last_timestamp=None)

    # Capture the actual range passed to make last_timestamp known.
    captured = {}

    def fake_fetch(name, symbol, interval_str, range_str):
        captured["range"] = range_str
        return FetchResult.ok_payload("eurusd", {"chart": {"result": [{}]}})

    monkeypatch.setattr(provider, "_fetch", fake_fetch)
    provider._fetch_intraday("eurusd", "EURUSD=X", last_timestamp=None)

    assert captured["range"] == "5d"


def test_intraday_range_incremental(provider, monkeypatch):
    provider.config["intraday_history_limit"] = "5d"

    # last_timestamp within 60 seconds → incremental → "1m"
    recent_ts = int(provider.now().timestamp()) - 60

    captured = {}

    def fake_fetch(name, symbol, interval_str, range_str):
        captured["range"] = range_str
        return FetchResult.ok_payload("eurusd", {"chart": {"result": [{}]}})

    monkeypatch.setattr(provider, "_fetch", fake_fetch)
    monkeypatch.setattr(provider, "_extract_candles", lambda results, fields=None, today=None: FetchResult.ok_payload("eurusd",[]))

    provider._fetch_intraday("eurusd", "EURUSD=X", last_timestamp=recent_ts)

    assert captured["range"] == "1m"


def test_intraday_range_exceeds_history_limit(provider, monkeypatch):
    # Configure a small history limit so we can exceed it easily
    provider.config["intraday_history_limit"] = "5d"

    # last_timestamp is 10 days old → older than 5d → must use history limit
    old_ts = int((provider.now() - timedelta(days=10)).timestamp())

    captured = {}

    def fake_fetch(name, symbol, interval_str, range_str):
        captured["range"] = range_str
        return FetchResult.ok_payload("eurusd", {"chart": {"result": [{}]}})

    monkeypatch.setattr(provider, "_fetch", fake_fetch)
    monkeypatch.setattr(provider, "_extract_candles", lambda results, fields=None, today=None: FetchResult.ok_payload("eurusd", []))

    provider._fetch_intraday("eurusd", "EURUSD=X", last_timestamp=old_ts)

    assert captured["range"] == "5d"
