# Copyright 2026 Rik Essenius
# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.
# File: tests/fetch/yahoo/test_candles.py


from datetime import UTC, datetime

from finance.common.model import DAILY, INTRADAY, CandlePoint, SeriesType

# ----------------------------------------------------------------------
# _extract_candles() tests (new provider)
# ----------------------------------------------------------------------


def test_extract_candles_valid_output_structure(yahoo_provider, unwrap, make_asset, make_series, fixed_now):
    """Full candle set → all fields extracted correctly."""

    now = fixed_now()
    asset = make_asset()
    series = make_series(asset, resolution=DAILY, series_type=SeriesType.CANDLE)
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

    candles = unwrap(yahoo_provider._extract_candles(series, result))

    assert len(candles) == 1
    c = candles[0]
    assert isinstance(c, CandlePoint)
    assert c.time == datetime(now.year, now.month, now.day, tzinfo=UTC)
    assert c.open == 1.0
    assert c.high == 2.0
    assert c.low == 0.5
    assert c.close == 1.5
    assert c.volume == 100


def test_extract_candles_skips_invalid(yahoo_provider, assert_warning, make_asset, make_series):
    """Invalid candle (None value) → skipped with warning."""

    result = {
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
    }

    asset = make_asset()
    series = make_series(asset, resolution=DAILY, series_type=SeriesType.CANDLE)

    candles = yahoo_provider._extract_candles(series, result)
    assert_warning(candles, "Skipped 1 invalid candles")
    assert candles.payload == []


def test_extract_candles_handles_missing_timestamp(yahoo_provider, assert_error, make_asset, make_series):
    """Missing timestamp array → fail."""

    result = {"timestamp": [], "indicators": {"quote": []}}

    asset = make_asset()
    series = make_series(asset, resolution=DAILY, series_type=SeriesType.VALUE)

    candles = yahoo_provider._extract_candles(series, result)
    assert_error(candles, "no timestamp in result", None)


def test_extract_candles_handles_missing_quote(yahoo_provider, assert_error, make_asset, make_series):
    """Missing quote structure → fail."""

    result = {"timestamp": [1], "indicators": {"quote": []}}
    asset = make_asset()

    series = make_series(asset, resolution=DAILY, series_type=SeriesType.CANDLE)

    candles = yahoo_provider._extract_candles(series, result)
    assert_error(candles, "unexpected quote structure", "missing index [0]")


def test_extract_candles_empty_result(yahoo_provider, unwrap, make_asset, make_series):
    """Quote exists but contains no arrays → empty candle list."""

    data = {"timestamp": [1], "indicators": {"quote": [{}]}}
    asset = make_asset()
    series = make_series(asset, resolution=INTRADAY, series_type=SeriesType.VALUE)
    candles = unwrap(yahoo_provider._extract_candles(series, data))
    assert candles == []
