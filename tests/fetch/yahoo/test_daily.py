# Copyright 2026 Rik Essenius
# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.
# File: tests/fetch/yahoo/test_daily.py

import datetime
from datetime import UTC, timedelta
from unittest.mock import Mock

from finance.common.model import FetchResult, MeasurementResult, Result

# ----------------------------------------------------------------------
# Daily tests
# ----------------------------------------------------------------------


def test_daily_no_missing_days(provider, unwrap):
    today_ts = int(provider.now().timestamp())
    result = unwrap(provider._fetch_daily("a", "EURUSD=X", ["close"], last_timestamp=today_ts))
    assert result == []


def test_daily_missing_days_triggers_fetch(provider, capture_fetch, make_payload, unwrap):
    payload = make_payload(
        [1704825600],
        {"open": [1.1], "high": [1.2], "low": [1.0], "close": [1.15], "volume": [1000]},
    )

    captured = capture_fetch(provider, payload)

    yesterday_ts = int(datetime.datetime(2024, 1, 9, 12, 0, tzinfo=UTC).timestamp())
    result = unwrap(provider._fetch_daily("b", "EURUSD=X", ["open", "close"], last_timestamp=yesterday_ts))

    assert captured["interval"] == "1d"
    assert captured["range"] == "1d"
    assert result[0].timestamp == 1704825600
    assert result[0].fields["open"] == 1.1
    assert result[0].fields["close"] == 1.15


def test_daily_skips_today_candles(provider, capture_fetch, make_payload):
    today_midnight = datetime.datetime(2024, 1, 10, 0, 0, tzinfo=UTC)
    ts = int(today_midnight.timestamp())

    payload = make_payload(
        [ts],
        {"open": [1.1], "high": [1.2], "low": [1.0], "close": [1.15], "volume": [1000]},
    )

    capture_fetch(provider, payload)

    yesterday_ts = int(datetime.datetime(2024, 1, 9, 12, 0, tzinfo=UTC).timestamp())
    result = provider._fetch_daily("c", "EURUSD=X", ["close"], last_timestamp=yesterday_ts)

    assert result.payload == []


def test_daily_invalid_candles_filtered(provider, capture_fetch, make_payload):
    payload = make_payload(
        [1704825600],
        {"open": [None], "high": [1.2], "low": [1.0], "close": [1.15], "volume": [1000]},
    )

    capture_fetch(provider, payload)

    yesterday_ts = int(datetime.datetime(2024, 1, 9, 12, 0, tzinfo=UTC).timestamp())
    result = provider._fetch_daily("d", "EURUSD=X", ["open", "close"], last_timestamp=yesterday_ts)

    assert result.payload == []


def test_daily_fetch_failure(provider, monkeypatch):
    monkeypatch.setattr(provider, "_fetch", lambda *args, **kwargs: FetchResult.fail("x", "failed", "network error"))

    yesterday_ts = int(datetime.datetime(2024, 1, 9, 12, 0, tzinfo=UTC).timestamp())
    result = provider._fetch_daily("e", "EURUSD=X", ["close"], last_timestamp=yesterday_ts)

    assert not result.ok
    assert result.payload is None
    assert result.reason == "failed"
    assert result.error == "network error"


def test_daily_range_selection_none(provider, monkeypatch):

    mock = Mock()

    monkeypatch.setattr(provider, "_fetch", mock)

    # Not missing a day → range should be None and fetch not called
    today_ts = int(datetime.datetime(2024, 1, 10, 12, 0, tzinfo=UTC).timestamp())

    provider._fetch_daily("f", "EURUSD=X", ["close"], last_timestamp=today_ts)

    mock.assert_not_called()


def test_daily_range_exceeds_history_limit(provider, monkeypatch):
    # Configure a small history limit so we can exceed it easily
    provider.config["daily_history_limit"] = "5d"

    # last_timestamp is 10 days old → older than 5d → must use history limit
    old_ts = int((provider.now() - timedelta(days=10)).timestamp())

    captured = {}

    def fake_fetch(name, symbol, interval_str, range_str):
        captured["range"] = range_str
        return Result.ok_payload({"chart": {"result": [{}]}})

    monkeypatch.setattr(provider, "_fetch", fake_fetch)
    monkeypatch.setattr(provider, "_extract_candles", lambda data, symbol, today=None: [])

    provider._fetch_daily("g", "EURUSD=X", ["close"], last_timestamp=old_ts)

    assert captured["range"] == "5d"


def test_daily_range_initial_load(provider, monkeypatch):
    # Configure a small history limit so we can assert against it
    provider.config["daily_history_limit"] = "5d"

    captured = {}

    def fake_fetch(name, symbol, interval_str, range_str):
        captured["range"] = range_str
        return FetchResult.ok_payload("h", {"chart": {"result": [{}]}})

    monkeypatch.setattr(provider, "_fetch", fake_fetch)
    monkeypatch.setattr(
        provider, "_extract_candles", lambda data, symbol, today=None: MeasurementResult.ok_payload("h", [])
    )

    # last_timestamp=None → initial load → must use history limit
    provider._fetch_daily("h", "EURUSD=X", ["close"], last_timestamp=None)

    assert captured["range"] == "5d"
