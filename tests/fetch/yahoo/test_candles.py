# Copyright 2026 Rik Essenius
# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.
# File: tests/fetch/yahoo/test_candles.py


from datetime import UTC, datetime

from finance.common.model import Retention, SeriesPoint, SeriesType

# ----------------------------------------------------------------------
# _extract_candles() tests (new provider)
# ----------------------------------------------------------------------


def normalize(input: int) -> datetime:
    return datetime.fromtimestamp(input, tz=UTC)


def test_extract_candles_valid_output_structure(yahoo_provider, unwrap, make_asset, make_series, fixed_now):
    """Full candle set → all fields extracted correctly."""

    now = fixed_now()
    asset = make_asset()
    series = make_series(asset, retention=Retention.LONG_LIVED, series_type=SeriesType.CANDLE, interval="1d")
    result = {
        "timestamp": [now.timestamp()],
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
    }

    candles = unwrap(yahoo_provider._extract_candles(series, normalize, result))

    assert len(candles) == 1
    point = candles[0]
    assert isinstance(point, SeriesPoint)
    assert point.time == fixed_now()  # because of the custom normalize
    assert point.open == 1.0
    assert point.high == 2.0
    assert point.low == 0.5
    assert point.close == 1.5
    assert point.volume == 100


def test_extract_candles_skips_invalid(yahoo_provider, assert_warning, make_asset, make_series):
    """Invalid candle (None value) → skipped with warning."""

    result = {
        "timestamp": [1000],
        "indicators": {
            "quote": [
                {
                    "open": [None],
                    "high": [None],
                    "low": [None],
                    "close": [None],  # invalid candle
                    "volume": [None],
                }
            ]
        },
    }

    asset = make_asset()
    series = make_series(asset, series_type=SeriesType.CANDLE)

    candles = yahoo_provider._extract_candles(series, normalize, result)
    assert_warning(candles, "Skipped 1 candles without close value")
    assert candles.payload == []


def test_extract_candles_signals_incomplete(yahoo_provider, assert_warning, make_asset, make_series):
    """Invalid candle (None value) → skipped with warning."""

    result = {
        "timestamp": [1000],
        "indicators": {
            "quote": [
                {
                    "open": [None],  # incomplete candle
                    "high": [2.0],
                    "low": [0.5],
                    "close": [1.5],
                    "volume": [100],
                }
            ]
        },
    }

    asset = make_asset()
    series = make_series(asset, series_type=SeriesType.CANDLE)

    candles = yahoo_provider._extract_candles(series, normalize, result)
    assert_warning(candles, "1 incomplete candles")
    assert len(candles.payload) == 1
    point = candles.payload[0]
    assert point.close == 1.5
    assert point.open is None


def test_extract_candles_handles_missing_timestamp(yahoo_provider, assert_error, make_asset, make_series):
    """Missing timestamp array → fail."""

    result = {"timestamp": [], "indicators": {"quote": []}}

    asset = make_asset()
    series = make_series(asset, series_type=SeriesType.VALUE)

    candles = yahoo_provider._extract_candles(series, normalize, result)
    assert_error(candles, "no timestamp in result", None)


def test_extract_candles_handles_missing_quote(yahoo_provider, assert_error, make_asset, make_series):
    """Missing quote structure → fail."""

    result = {"timestamp": [1], "indicators": {"quote": []}}
    asset = make_asset()

    series = make_series(asset, series_type=SeriesType.CANDLE)

    candles = yahoo_provider._extract_candles(series, normalize, result)
    assert_error(candles, "unexpected quote structure", "missing index [0]")


def test_extract_candles_empty_result(yahoo_provider, unwrap, make_asset, make_series):
    """Quote exists but contains no arrays → empty candle list."""

    data = {"timestamp": [1], "indicators": {"quote": [{}]}}
    asset = make_asset()
    series = make_series(asset, series_type=SeriesType.VALUE)
    candles = unwrap(yahoo_provider._extract_candles(series, normalize, data))
    assert candles == []
