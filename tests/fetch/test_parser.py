# Copyright 2026 Rik Essenius
# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.
# File: tests/fetch/test_parser.py

import pytest

from finance.fetch.parser import parse_duration


def test_parse_duration_valid_units():
    assert parse_duration("10s") == 10
    assert parse_duration("5m") == 5 * 60
    assert parse_duration("2h") == 2 * 3600
    assert parse_duration("3d") == 3 * 86400
    assert parse_duration("1w") == 1 * 604800
    assert parse_duration("800000s") == 800000
    assert parse_duration("0s") == 0


@pytest.mark.parametrize("text", ["10", "5x", "1.5h", "5 d", "-5m", "", "abc", "h5", "5mm", "1hour", "P5D"])
def test_parse_duration_rejects_garbage(text):
    with pytest.raises(ValueError):
        parse_duration(text)
