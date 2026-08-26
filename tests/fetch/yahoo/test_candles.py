# Copyright 2026 Rik Essenius
# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.
# File: tests/fetch/yahoo/test_candles.py


from datetime import datetime

from finance.common.json_utils import JsonReader
from finance.common.model import SeriesPoint
from finance.common.string_enums import Retention, SeriesType
from finance.common.time_utils import UTC
from finance.fetch.yahoo import YahooProvider

# ----------------------------------------------------------------------
# _extract_candles() tests (new provider)
# ----------------------------------------------------------------------


def normalize(input: int) -> datetime:
    return datetime.fromtimestamp(input, tz=UTC)


def test_extract_candles_valid_output_structure(yahoo_provider, unwrap, make_asset, make_series):
    """Full candle set → all fields extracted correctly."""

    def fake_now():
        return datetime(2026, 7, 23, tzinfo=UTC)

    now = fake_now()
    asset = make_asset()
    series = make_series(asset, retention=Retention.LONG_LIVED, series_type=SeriesType.CANDLE, interval="1d")
    reader = JsonReader(
        {
            "timestamp": [int(now.timestamp())],
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
    )
    provider: YahooProvider = yahoo_provider(now_provider=fake_now)
    candles = unwrap(provider._extract_candles(series, reader))

    assert len(candles) == 1
    point = candles[0]
    assert isinstance(point, SeriesPoint)
    assert point.time == fake_now()  # because of the custom normalize
    assert point.open == 1.0
    assert point.high == 2.0
    assert point.low == 0.5
    assert point.close == 1.5
    assert point.volume == 100


def test_extract_candles_skips_invalid(yahoo_provider, assert_warning, make_asset, make_series):
    """Invalid candle (None value) → skipped with warning."""

    timestamp = int(datetime(2026, 7, 23, tzinfo=UTC).timestamp())
    reader = JsonReader(
        {
            "timestamp": [timestamp],
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
    )

    asset = make_asset()
    series = make_series(asset, series_type=SeriesType.CANDLE)

    provider: YahooProvider = yahoo_provider()
    candles = provider._extract_candles(series, reader)
    assert_warning(candles, "Skipped 1 candles without close value")
    assert candles.ok is True
    assert candles.payload == []


def test_extract_candles_signals_incomplete(yahoo_provider, assert_warning, make_asset, make_series):
    """Invalid candle (None value) → skipped with warning."""

    timestamp = int(datetime(2026, 7, 23, tzinfo=UTC).timestamp())

    reader = JsonReader(
        {
            "timestamp": [timestamp],
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
    )

    asset = make_asset()
    series = make_series(asset, series_type=SeriesType.CANDLE)
    provider: YahooProvider = yahoo_provider()
    candles = provider._extract_candles(series, reader)
    assert_warning(candles, "1 incomplete candles")
    assert candles.ok is True
    assert len(candles.payload) == 1
    point = candles.payload[0]
    assert point.close == 1.5
    assert point.open is None


def test_extract_candles_handles_missing_timestamp(yahoo_provider, make_asset, make_series):
    """Missing timestamp array → fail."""

    reader = JsonReader({"timestamp": [], "indicators": {"quote": []}})

    asset = make_asset()
    series = make_series(asset, series_type=SeriesType.VALUE)
    provider: YahooProvider = yahoo_provider()
    candles = provider._extract_candles(series, reader)
    assert candles.ok is True
    assert candles.payload == []
    assert candles.warnings[0] == "no timestamp in result"


def test_extract_candles_empty_result(yahoo_provider, unwrap, make_asset, make_series):
    """Quote exists but contains no arrays → empty candle list."""

    reader = JsonReader({"timestamp": [1], "indicators": {"quote": [{}]}})
    asset = make_asset()
    provider: YahooProvider = yahoo_provider()
    series = make_series(asset, series_type=SeriesType.VALUE)
    candles = unwrap(provider._extract_candles(series, reader))
    assert candles == []
