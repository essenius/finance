# Copyright 2026 Rik Essenius
# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.
# File: tests/fetch/yahoo/test_candles.py


from datetime import datetime

from finance.common.json_utils import JsonReader
from finance.common.model import Asset, Series, SeriesPoint, SeriesPoints
from finance.common.string_enums import Retention, SeriesType
from finance.common.time_utils import UTC
from finance.common.types import Unwrap
from finance.fetch.yahoo import YahooProvider
from tests.support.fakes import FakeProvider
from tests.support.types import AssertWarning, Creator, Factory

type YahooFakeSession = FakeProvider[YahooProvider]

# ----------------------------------------------------------------------
# _extract_candles() tests (new provider)
# ----------------------------------------------------------------------


def normalize(input: int) -> datetime:
    return datetime.fromtimestamp(input, tz=UTC)


def test_extract_candles_valid_output_structure(
    yahoo_provider: Creator[YahooFakeSession],
    unwrap: Unwrap[SeriesPoints],
    make_asset: Creator[Asset],
    make_series: Creator[Series],
):
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
    fake = yahoo_provider(now_provider=fake_now)
    candles = unwrap(fake.provider._extract_candles(series, reader))

    assert len(candles) == 1
    point = candles[0]
    assert isinstance(point, SeriesPoint)
    assert point.time == fake_now()  # because of the custom normalize
    assert point.open == 1.0
    assert point.high == 2.0
    assert point.low == 0.5
    assert point.close == 1.5
    assert point.volume == 100


def test_extract_candles_skips_invalid(
    yahoo_provider: Factory[YahooFakeSession],
    assert_warning: AssertWarning,
    make_asset: Creator[Asset],
    make_series: Creator[Series],
):
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

    fake = yahoo_provider()
    candles = fake.provider._extract_candles(series, reader)
    assert_warning(candles, "Skipped 1 candles without close value")
    assert candles.ok is True
    assert candles.payload == []


def test_extract_candles_signals_incomplete(
    yahoo_provider: Factory[YahooFakeSession],
    assert_warning: AssertWarning,
    make_asset: Creator[Asset],
    make_series: Creator[Series],
):
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
    fake = yahoo_provider()
    candles = fake.provider._extract_candles(series, reader)
    assert_warning(candles, "1 incomplete candles")
    assert candles.ok is True
    assert len(candles.payload) == 1
    point = candles.payload[0]
    assert point.close == 1.5
    assert point.open is None


def test_extract_candles_handles_missing_timestamp(
    yahoo_provider: Factory[YahooFakeSession], make_asset: Creator[Asset], make_series: Creator[Series]
):
    """Missing timestamp array → fail."""

    reader = JsonReader({"timestamp": [], "indicators": {"quote": []}})

    asset = make_asset()
    series = make_series(asset, series_type=SeriesType.VALUE)
    fake = yahoo_provider()
    candles = fake.provider._extract_candles(series, reader)
    assert candles.ok is True
    assert candles.payload == []
    assert candles.warnings[0] == "no timestamp in result"


def test_extract_candles_empty_result(
    yahoo_provider: Factory[YahooFakeSession],
    unwrap: Unwrap[SeriesPoints],
    make_asset: Creator[Asset],
    make_series: Creator[Series],
):
    """Quote exists but contains no arrays → empty candle list."""

    reader = JsonReader({"timestamp": [1], "indicators": {"quote": [{}]}})
    asset = make_asset()
    fake = yahoo_provider()
    series = make_series(asset, series_type=SeriesType.VALUE)
    candles = unwrap(fake.provider._extract_candles(series, reader))
    assert candles == []
