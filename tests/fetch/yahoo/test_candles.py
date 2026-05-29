# Copyright 2026 Rik Essenius
# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.
# File: tests/fetch/yahoo/test_candles.py

from datetime import UTC, date, datetime

from finance.fetch.model import Candle
from finance.fetch.yahoo import CandleSeries

# ----------------------------------------------------------------------
# CandleSeries tests
# ----------------------------------------------------------------------


def test_candle_series_iterates_correctly():
    series = CandleSeries(
        timestamps=[1, 2],
        opens=[10.0, 20.0],
        highs=[15.0, 25.0],
        lows=[5.0, 15.0],
        closes=[12.0, 22.0],
        volumes=[100, 200],
    )

    candles = list(series)

    assert len(candles) == 2
    assert isinstance(candles[0], Candle)
    assert candles[0].timestamp == 1
    assert candles[0].open == 10.0
    assert candles[1].timestamp == 2
    assert candles[1].close == 22.0


def test_candle_series_empty_lists():
    series = CandleSeries([], [], [], [], [], [])
    candles = list(series)
    assert candles == []


def test_candle_series_mismatched_lengths_zip_truncates():
    series = CandleSeries(
        timestamps=[1, 2, 3],
        opens=[10.0, 20.0],
        highs=[15.0, 25.0],
        lows=[5.0, 15.0],
        closes=[12.0, 22.0],
        volumes=[100, 200],
    )

    candles = list(series)

    # zip() truncates to the shortest list → 2 items
    assert len(candles) == 2
    assert candles[0].timestamp == 1
    assert candles[1].timestamp == 2


def test_candle_series_produces_valid_candles():
    series = CandleSeries(
        timestamps=[100],
        opens=[1.1],
        highs=[1.2],
        lows=[1.0],
        closes=[1.15],
        volumes=[500],
    )

    candle = next(iter(series))
    assert candle.is_valid() is True


# ----------------------------------------------------------------------
# _extract_candles() tests
# ----------------------------------------------------------------------


def test_extract_candles_valid_output_structure(provider):

    result = {
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
        # }]
    }

    candles = provider._extract_candles(result, "x")

    assert len(candles) == 1
    c = candles[0]
    assert c["timestamp"] == 1000
    assert c["fields"]["open"] == 1.0
    assert c["fields"]["close"] == 1.5


def test_extract_candles_skips_invalid(provider, capsys):

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

    candles = provider._extract_candles(result, "x")
    assert candles == []
    assert "invalid candle: {" in capsys.readouterr().err


def test_extract_candles_filters_today(provider, capsys):

    today = date(2026, 5, 25)
    today_midnight = int(datetime(today.year, today.month, today.day, tzinfo=UTC).timestamp())

    result = {
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
    }

    candles = provider._extract_candles(result, "x", today=today)
    assert candles == []
    assert capsys.readouterr().err == ""


def test_extract_candles_handles_missing_timestamp(provider, capsys):

    result = {"timestamp": [], "indicators": {"quote": []}}

    candles = provider._extract_candles(result, "x")
    assert candles == []

    assert "no timestamp in result" in capsys.readouterr().err


def test_extract_candles_handles_missing_quote(provider, capsys):

    result = {"timestamp": [1], "indicators": {"quote": []}}

    candles = provider._extract_candles(result, "x")
    assert candles == []

    assert "missing index [0] in path for quote list" in capsys.readouterr().err


def test_extract_candles_empty_result(provider, capsys):

    data = {
        "timestamp": [1],
        "indicators": {"quote": [{}]},  # missing arrays → treated as empty lists
    }

    candles = provider._extract_candles(data, "x")
    assert candles == []
    assert capsys.readouterr().err == ""
