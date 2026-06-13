# Copyright 2026 Rik Essenius
# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.
# File: tests/fetch/yahoo/test_candles.py

from unittest.mock import Mock

from finance.common.model import MeasurementResult

# ----------------------------------------------------------------------
# _extract_candles() tests (new provider)
# ----------------------------------------------------------------------


def test_extract_candles_valid_output_structure(yahoo_provider, unwrap):
    """Full candle set → all fields extracted correctly."""

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

    candles = unwrap(yahoo_provider._extract_candles(result))

    assert len(candles) == 1
    c = candles[0]
    assert c.timestamp == 1000
    assert c.fields == {
        "open": 1.0,
        "high": 2.0,
        "low": 0.5,
        "close": 1.5,
        "volume": 100,
    }


def test_extract_candles_filter_fields(yahoo_provider, unwrap):
    """Subset of candle fields → only those fields appear."""

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

    candles = unwrap(yahoo_provider._extract_candles(result, ["open", "close"]))

    assert len(candles) == 1
    c = candles[0]
    assert c.timestamp == 1000
    assert c.fields == {"open": 1.0, "close": 1.5}


def test_extract_candles_skips_invalid(yahoo_provider, assert_warning):
    """Invalid candle (None value) → skipped with warning."""

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

    candles = yahoo_provider._extract_candles(result)
    assert_warning(candles, "Skipped 1 invalid candles")
    assert candles.payload == []


def test_extract_candles_handles_missing_timestamp(yahoo_provider, assert_error):
    """Missing timestamp array → fail."""

    result = MeasurementResult.ok_payload("z", {"timestamp": [], "indicators": {"quote": []}})

    candles = yahoo_provider._extract_candles(result, ["open"])
    assert_error(candles, "no timestamp in result", None)


def test_extract_candles_handles_missing_quote(yahoo_provider, assert_error):
    """Missing quote structure → fail."""

    result = MeasurementResult.ok_payload("y", {"timestamp": [1], "indicators": {"quote": []}})

    candles = yahoo_provider._extract_candles(result)
    assert_error(candles, "unexpected quote structure", "missing index [0]")


def test_extract_candles_empty_result(yahoo_provider, unwrap):
    """Quote exists but contains no arrays → empty candle list."""

    data = MeasurementResult.ok_payload(
        "v",
        {"timestamp": [1], "indicators": {"quote": [{}]}},
    )

    candles = unwrap(yahoo_provider._extract_candles(data))
    assert candles == []


def test_extract_candles_resolve_field_mapping_fails(yahoo_provider, assert_error):
    payload = {
        "timestamp": [1000],
        "indicators": {"quote": [{"close": [10.0]}]},
    }
    results = Mock()
    results.measurement = "m"
    results.payload = payload

    result = yahoo_provider._extract_candles(results, ["close", "foo"])
    assert_error(result, "Unsupported field combination: ['close', 'foo']", None)


def test_resolve_field_mapping_single_unknown_field(yahoo_provider, unwrap):
    result = yahoo_provider._resolve_field_mapping(["foo"])
    selected, mapped = unwrap(result)
    assert selected == ["close"]
    assert mapped == ["foo"]
