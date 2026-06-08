# Copyright 2026 Rik Essenius
# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.
# File: tests/fetch/yahoo/test_candles.py

from datetime import UTC, date, datetime

from finance.common.model import MeasurementResult

# ----------------------------------------------------------------------
# _extract_candles() tests
# ----------------------------------------------------------------------


def test_extract_candles_valid_output_structure(provider, unwrap):

    result = MeasurementResult.ok_payload(
        "x",
        {
            "timestamp": [1000],
            "indicators": {
                "quote": [
                    {
                        "open": [1.0],
                        "high": [2.0],
                        "low": [0.5],
                        "close": [1.5],
                        "volume": [100],
                    }
                ]
            },
        },
    )

    candles = unwrap(provider._extract_candles(result))

    assert len(candles) == 1
    c = candles[0]
    assert c.timestamp == 1000
    assert c.fields["open"] == 1.0
    assert c.fields["high"] == 2.0
    assert c.fields["low"] == 0.5
    assert c.fields["close"] == 1.5
    assert c.fields["volume"] == 100


def test_extract_candles_filter_fields(provider, unwrap):

    result = MeasurementResult.ok_payload(
        "x",
        {
            "timestamp": [1000],
            "indicators": {
                "quote": [
                    {
                        "open": [1.0],
                        "high": [2.0],
                        "low": [0.5],
                        "close": [1.5],
                        "volume": [100],
                    }
                ]
            },
        },
    )

    candles = unwrap(provider._extract_candles(result, ["open", "close"]))

    assert len(candles) == 1
    c = candles[0]
    assert c.timestamp == 1000
    assert c.fields["open"] == 1.0
    assert c.fields.get("high") is None
    assert c.fields.get("low") is None
    assert c.fields["close"] == 1.5
    assert c.fields.get("volume") is None


def test_extract_candles_empty_mapping(provider):

    result = MeasurementResult.ok_payload(
        "x",
        {
            "timestamp": [1000],
            "indicators": {
                "quote": [
                    {
                        "open": [1.0],
                        "high": [2.0],
                        "low": [0.5],
                        "close": [1.5],
                        "volume": [100],
                    }
                ]
            },
        },
    )

    candles = provider._extract_candles(result, ["hoog", "laag"])
    assert not candles.ok
    assert (
        "Unknown fields requested: ['hoog', 'laag']. Supported: ['open', 'high', 'low', 'close', 'volume']"
        in candles.reason
    )


def test_extract_candles_skips_invalid(provider, unwrap):

    result = MeasurementResult.ok_payload(
        "u",
        {
            "timestamp": [1000],
            "indicators": {
                "quote": [
                    {
                        "open": [None],  # invalid candle
                        "high": [2.0],
                        "low": [0.5],
                        "close": [1.5],
                        "volume": [100],
                    }
                ]
            },
        },
    )

    candles = provider._extract_candles(result)
    assert candles.ok
    assert "Skipped 1 invalid candles" in candles.warning
    assert candles.payload == []


def test_extract_candles_filters_today(provider, unwrap):

    today = date(2026, 5, 25)
    today_midnight = int(datetime(today.year, today.month, today.day, tzinfo=UTC).timestamp())

    result = MeasurementResult.ok_payload(
        "t",
        {
            "timestamp": [today_midnight + 60],  # candle from today → must be skipped
            "indicators": {
                "quote": [
                    {
                        "open": [1.0],
                        "high": [2.0],
                        "low": [0.5],
                        "close": [1.5],
                        "volume": [100],
                    }
                ]
            },
        },
    )

    candles = unwrap(provider._extract_candles(result, None, today=today))
    assert candles == []


def test_extract_candles_handles_missing_timestamp(provider, assert_error):

    result = MeasurementResult.ok_payload("z", {"timestamp": [], "indicators": {"quote": []}})

    candles = provider._extract_candles(result, ["open"])
    assert_error(candles, "no timestamp in result", None)


def test_extract_candles_handles_missing_quote(provider, assert_error):

    result = MeasurementResult.ok_payload("y", {"timestamp": [1], "indicators": {"quote": []}})

    candles = provider._extract_candles(result)
    assert_error(candles, "unexpected quote structure", "missing index [0] at [")


def test_extract_candles_empty_result(provider, unwrap):

    # missing arrays → treated as empty lists
    data = MeasurementResult.ok_payload("v", {"timestamp": [1], "indicators": {"quote": [{}]}})

    candles = unwrap(provider._extract_candles(data))
    assert candles == []
