# Copyright 2026 Rik Essenius
# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.
# File: tests/common/test_time_utils.py

from datetime import UTC, datetime, timedelta

import pytest

from finance.common.time_utils import check_duration_in, normalize_db_time, parse_duration

# ---------------
# Parse duration
# ---------------


def test_parse_duration_valid():
    assert parse_duration("10s") == timedelta(seconds=10)
    assert parse_duration("500m") == timedelta(minutes=500)
    assert parse_duration("2h") == timedelta(hours=2)
    assert parse_duration("1d") == timedelta(days=1)
    assert parse_duration("10w") == timedelta(weeks=10)
    # years is an approximation: 365.25 days
    assert parse_duration("4y") == timedelta(days=365.25 * 4)
    assert parse_duration("0") == timedelta(0)


@pytest.mark.parametrize("text", ["10", "5x", "1.5h", "5 d", "-5m", "", "abc", "h5", "5mm", "1hour", "P5D"])
def test_parse_duration_rejects_garbage(text):
    with pytest.raises(ValueError) as exc_info:
        parse_duration(text, "test")
    assert f"Invalid duration '{text}' in test" in str(exc_info.value)


def test_parse_duration_accepts_no_context():
    with pytest.raises(ValueError) as exc_info:
        parse_duration("qx")
    assert str(exc_info.value) == "Invalid duration 'qx'"


def test_check_duration_in():
    input = {"test1": "1d", "test3": "qx"}
    assert check_duration_in(input, "test1") == "1d"
    assert check_duration_in(input, "test2") is None
    with pytest.raises(ValueError) as exc_info:
        check_duration_in(input, "test3")
    assert str(exc_info.value) == "Invalid duration 'qx' in test3"


def test_normalize_db_time_datetime(fixed_now):
    now = fixed_now()
    result = normalize_db_time(now)
    assert result == now


def test_normalize_db_time_date(fixed_now):
    now = fixed_now()
    today = now.date()
    result = normalize_db_time(today)
    assert result == datetime(now.year, now.month, now.day, 0, 0, 0, tzinfo=UTC)


def test_normalize_db_time_error():
    with pytest.raises(TypeError) as exc_info:
        normalize_db_time("qx")
    assert str(exc_info.value) == "Unexpected time type: <class 'str'>"
