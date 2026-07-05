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


# ----------------
# to UTC Midnight
# ----------------

"""
TODO delete if no longer needed
def test_to_utc_midnight_chicago_summer():
    tz = ZoneInfo("America/Chicago")
    local_dt = datetime(2024, 5, 9, 0, 0, tzinfo=tz)

    time = to_utc_midnight(local_dt)

    # 2024-05-09 00:00 CDT = 2024-05-09 05:00 UTC → snapped to 00:00 UTC
    assert time == datetime(2024, 5, 10, 0, 0, tzinfo=UTC)


def test_to_utc_midnight_chicago_winter():
    tz = ZoneInfo("America/Chicago")
    local_dt = datetime(2024, 1, 15, 0, 0, tzinfo=tz)

    time = to_utc_midnight(local_dt)

    # 2024-01-15 00:00 CST = 2024-01-15 06:00 UTC → snapped to 00:00 UTC
    assert time == datetime(2024, 1, 16, 0, 0, tzinfo=UTC)


def test_to_utc_midnight_chicago_dst_start():
    tz = ZoneInfo("America/Chicago")
    # DST starts March 10, 2024
    local_dt = datetime(2024, 3, 10, 0, 0, tzinfo=tz)

    time = to_utc_midnight(local_dt)

    # 2024-03-10 00:00 CST = 2024-03-10 06:00 UTC → snapped to 00:00 UTC
    assert time == datetime(2024, 3, 11, 0, 0, tzinfo=UTC)


def test_to_utc_midnight_chicago_dst_end():
    tz = ZoneInfo("America/Chicago")
    # DST ends Nov 3, 2024
    local_dt = datetime(2024, 11, 3, 0, 0, tzinfo=tz)

    time = to_utc_midnight(local_dt)

    # 2024-11-03 00:00 CDT = 2024-11-03 05:00 UTC → snapped to 00:00 UTC
    assert time == datetime(2024, 11, 4, 0, 0, tzinfo=UTC)


def test_to_utc_midnight_frankfurt():
    tz = ZoneInfo("Europe/Berlin")
    local_dt = datetime(2024, 5, 9, 0, 0, tzinfo=tz)

    time = to_utc_midnight(local_dt)

    # 2024-05-09 00:00 CEST = 2024-05-08 22:00 UTC → snapped to 2024-05-09 00:00 UTC
    assert time == datetime(2024, 5, 9, 0, 0, tzinfo=UTC)


def test_to_utc_midnight_idempotent_for_utc():
    local_dt = datetime(2024, 5, 9, 12, 34, tzinfo=UTC)

    time = to_utc_midnight(local_dt)

    # Should snap to 2024-05-09 00:00 UTC
    assert time == datetime(2024, 5, 9, 0, 0, tzinfo=UTC)


def test_to_utc_midnight_australia():
    tz = ZoneInfo("Australia/Sydney")
    # Arbitrary date; Sydney is ahead of UTC
    local_dt = datetime(2024, 5, 9, 0, 0, tzinfo=tz)

    time = to_utc_midnight(local_dt)

    # Local midnight in Sydney corresponds to previous UTC date
    expected = datetime(2024, 5, 9, 0, 0, tzinfo=UTC)
    assert time == expected


def test_to_utc_midnight_hawaii():
    tz = ZoneInfo("Pacific/Honolulu")
    # Arbitrary date; Sydney is ahead of UTC
    local_dt = datetime(2024, 5, 9, 0, 0, tzinfo=tz)

    time = to_utc_midnight(local_dt)

    # Local midnight in Sydney corresponds to previous UTC date
    expected = datetime(2024, 5, 10, 0, 0, tzinfo=UTC)
    assert time == expected
"""


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
