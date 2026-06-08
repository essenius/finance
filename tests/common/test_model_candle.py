# Copyright 2026 Rik Essenius
# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.
# File: tests/fetch/test_model_candle.py

import pytest

from finance.common.model import Candle


def test_candle_valid():
    candle = Candle(
        timestamp=123,
        open=1.0,
        high=2.0,
        low=0.5,
        close=1.5,
        volume=1000,
    )
    assert candle.is_valid() is True

    point = candle.to_point()
    assert point.timestamp == 123
    assert point.fields["open"] == 1.0
    assert point.fields["high"] == 2.0
    assert point.fields["low"] == 0.5
    assert point.fields["close"] == 1.5
    assert point.fields["volume"] == 1000
    assert len(point.fields) == 5


@pytest.mark.parametrize("field", ["timestamp", "open", "high", "low", "close", "volume"])
def test_candle_invalid_fields(field):
    kwargs = {
        "timestamp": 123,
        "open": 1.0,
        "high": 2.0,
        "low": 0.5,
        "close": 1.5,
        "volume": 1000,
    }
    kwargs[field] = None

    candle = Candle(**kwargs)
    assert candle.is_valid() is False


@pytest.mark.parametrize(
    "fields, expected",
    [
        # subset
        (["open", "close"], {"open": 1, "close": 4}),
        # non-candle and non-provided ignored
        (["price", "open"], {"open": 1}),
        # unknown field ignored
        (["foo"], {}),
    ],
)
def test_candle_to_point_fields_param(fields, expected):
    candle = Candle(timestamp=0, open=1, high=2, low=3, close=4, volume=5)
    result = candle.to_point(fields)
    assert result.fields == expected
