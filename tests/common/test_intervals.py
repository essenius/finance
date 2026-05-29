# Copyright 2026 Rik Essenius
# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.
# File: tests/common/test_intervals.py

import pytest

from finance.common.intervals import parse_interval


def test_parse_interval_valid():
    assert parse_interval("10s") == 10
    assert parse_interval("500m") == 30000
    assert parse_interval("2h") == 7200
    assert parse_interval("1d") == 86400


def test_parse_interval_invalid_value():
    with pytest.raises(ValueError):
        parse_interval("xh")

    with pytest.raises(ValueError):
        parse_interval("m")

    with pytest.raises(ValueError):
        parse_interval("")


def test_parse_interval_invalid_unit():
    with pytest.raises(ValueError):
        parse_interval("10w")

    with pytest.raises(ValueError):
        parse_interval("10H")  # uppercase not allowed
