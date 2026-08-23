# Copyright 2026 Rik Essenius
# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.
# File: tests/common/test_time_utils.py

from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

import pytest

from finance.common.guards import require
from finance.common.time_utils import (
    UTC,
    normalize_db_time,
    now_second_precision,
    parse_datetime,
    parse_duration,
    parse_time,
    parse_timezone,
    parse_weekday,
    snap_to,
    validate_duration,
    write_datetime,
    write_time,
    write_timezone,
)

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


def test_validate_duration():
    assert validate_duration("1d", "test") == "1d"
    assert validate_duration(None, "test") is None
    with pytest.raises(ValueError) as exc_info:
        validate_duration("qx", "test")
    assert str(exc_info.value) == "Invalid duration 'qx' in test"


def test_normalize_db_time_datetime(fixed_now):
    now = fixed_now()
    assert normalize_db_time(now) == now

    naive_now = datetime(2026, 7, 14)
    assert normalize_db_time(naive_now) == datetime(2026, 7, 14, tzinfo=UTC)


def test_normalize_db_time_date(fixed_now):
    now = fixed_now()
    today = now.date()
    result = normalize_db_time(today)
    assert result == datetime(now.year, now.month, now.day, 0, 0, 0, tzinfo=UTC)


def test_normalize_db_time_error():
    with pytest.raises(TypeError) as exc_info:
        normalize_db_time("qx")
    assert str(exc_info.value) == "Unexpected time type: <class 'str'>"


def test_parse_weekday():
    assert parse_weekday("sat") == 5
    with pytest.raises(ValueError) as exc_info:
        parse_weekday("bogus")
    assert str(exc_info.value) == "Cannot understand day 'bogus'."


def test_parse_write_time():
    assert write_time(None) is None
    time_str = write_time(time.min)
    assert time_str == "00:00:00"
    assert parse_time("min") == time.min

    time_str = write_time(time.max)
    assert time_str == "23:59:59.999999"
    assert parse_time("max") == time.max

    a_time = require(parse_time(955), "a_time")  # 15:55 in sexagesimal
    assert a_time == time(hour=15, minute=55)
    assert write_time(a_time) == "15:55:00", "writing always in seconds"

    a_datetime = require(parse_time("9:00:05"), "a_datetime")
    assert a_datetime == time(hour=9, second=5), "string parsing uses seconds too"
    time_str = write_time(a_datetime)
    assert time_str == "09:00:05"
    assert parse_time(time_str) == a_datetime

    with pytest.raises(ValueError) as exc_info:
        parse_time(58230)  # 16:10:30"
    assert str(exc_info.value) == "Cannot understand sexagesimal value '58230' (970:30). Use hh:mm only or use quotes."
    with pytest.raises(ValueError) as exc_info:
        parse_time("bogus")
    assert str(exc_info.value) == "Cannot understand time 'bogus'."


def test_snap_to():
    base = datetime(2026, 7, 10, 9, 30, tzinfo=UTC)
    interval = timedelta(minutes=15)
    assert snap_to(base, interval) == base, "base"
    highest_snapped_back = snap_to(base + interval - timedelta(seconds=1), interval)
    assert highest_snapped_back == base, "base highest snapped back"
    assert snap_to(base + interval, interval) == base + interval, "next snap"


def test_now_second_precision():
    now = datetime.now(tz=UTC)
    on_seconds = now_second_precision()
    assert on_seconds.microsecond == 0
    assert now - on_seconds < timedelta(seconds=1)


def test_parse_write_timezone():
    assert write_timezone(None) is None

    timezone_str = "Pacific/Honolulu"
    timezone_obj = parse_timezone(timezone_str)
    assert timezone_obj == ZoneInfo(timezone_str)
    assert write_timezone(timezone_obj) == timezone_str

    timezone_str = write_timezone(UTC)
    assert timezone_str == "UTC"

    # note this is not orthogonal. Writing datetime.UTC returns ZoneInfo("UTC")
    # this is because datetime.UTC uses the legacy format without key
    utc = parse_timezone(timezone_str)
    assert utc.key == timezone_str

    with pytest.raises(ValueError) as exc_info:
        parse_timezone("bogus")
    assert str(exc_info.value) == "Cannot understand timezone 'bogus'."


def test_parse_write_datetime():
    dt = datetime(2026, 5, 16, 9, tzinfo=UTC)
    dt_str = write_datetime(dt)
    assert dt_str == "2026-05-16T09:00:00+00:00"
    assert parse_datetime(dt_str) == dt
    with pytest.raises(ValueError) as exc_info:
        parse_datetime("bogus")
    assert str(exc_info.value) == "Cannot understand datetime 'bogus'."
