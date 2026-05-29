# Copyright 2026 Rik Essenius
# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.
# File: tests/fetch/test_model_candle.py

import pytest

from finance.fetch.model import Candle


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
