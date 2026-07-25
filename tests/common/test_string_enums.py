# Copyright 2026 Rik Essenius
# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.
# File: tests/common/test_string_enums.py

import pytest

from finance.common.string_enums import Candle, Retention, SeriesType


def test_stringenum_validate():
    with pytest.raises(ValueError) as exc_info:
        Retention.validate("bogus")
        assert "Invalid Retention: 'bogus'. Allowed: short_lived, long_lived" in exc_info


def test_stringenum_contains():
    assert Candle.contains("close")
    assert not Candle.contains("value")


def test_stringenum_values():
    assert SeriesType.values() == ["candle", "value"]


def test_candle_ordered():
    assert Candle.ordered() == ["open", "high", "low", "close", "volume"]
