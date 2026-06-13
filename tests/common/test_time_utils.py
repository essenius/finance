# Copyright 2026 Rik Essenius
# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.
# File: tests/common/test_time_utils.py

from datetime import UTC, datetime
from zoneinfo import ZoneInfo

import pytest

from finance.common.time_utils import parse_duration, to_utc_midnight

# ---------------
# Parse duration
# ---------------


def test_parse_duration_valid():
    assert parse_duration("10s") == 10
    assert parse_duration("500m") == 30000
    assert parse_duration("2h") == 7200
    assert parse_duration("1d") == 86400
    assert parse_duration("10w") == 6048000
    assert parse_duration("4y") == 126230400


@pytest.mark.parametrize("text", ["10", "5x", "1.5h", "5 d", "-5m", "", "abc", "h5", "5mm", "1hour", "P5D"])
def test_parse_duration_rejects_garbage(text):
    with pytest.raises(ValueError) as exc_info:
        parse_duration(text, "test")
    assert f"Invalid duration '{text}' in test" in str(exc_info.value)


def test_parse_duration_accepts_no_context():
    with pytest.raises(ValueError) as exc_info:
        parse_duration("qx")
    assert str(exc_info.value) == "Invalid duration 'qx'"


# ----------------
# to UTC Midnight
# ----------------


def test_to_utc_midnight_chicago_summer():
    tz = ZoneInfo("America/Chicago")
    local_dt = datetime(2024, 5, 9, 0, 0, tzinfo=tz)

    ts = to_utc_midnight(local_dt)

    # 2024-05-09 00:00 CDT = 2024-05-09 05:00 UTC → snapped to 00:00 UTC
    assert ts == int(datetime(2024, 5, 10, 0, 0, tzinfo=UTC).timestamp())


def test_to_utc_midnight_chicago_winter():
    tz = ZoneInfo("America/Chicago")
    local_dt = datetime(2024, 1, 15, 0, 0, tzinfo=tz)

    ts = to_utc_midnight(local_dt)

    # 2024-01-15 00:00 CST = 2024-01-15 06:00 UTC → snapped to 00:00 UTC
    assert ts == int(datetime(2024, 1, 16, 0, 0, tzinfo=UTC).timestamp())


def test_to_utc_midnight_chicago_dst_start():
    tz = ZoneInfo("America/Chicago")
    # DST starts March 10, 2024
    local_dt = datetime(2024, 3, 10, 0, 0, tzinfo=tz)

    ts = to_utc_midnight(local_dt)

    # 2024-03-10 00:00 CST = 2024-03-10 06:00 UTC → snapped to 00:00 UTC
    assert ts == int(datetime(2024, 3, 11, 0, 0, tzinfo=UTC).timestamp())


def test_to_utc_midnight_chicago_dst_end():
    tz = ZoneInfo("America/Chicago")
    # DST ends Nov 3, 2024
    local_dt = datetime(2024, 11, 3, 0, 0, tzinfo=tz)

    ts = to_utc_midnight(local_dt)

    # 2024-11-03 00:00 CDT = 2024-11-03 05:00 UTC → snapped to 00:00 UTC
    assert ts == int(datetime(2024, 11, 4, 0, 0, tzinfo=UTC).timestamp())


def test_to_utc_midnight_frankfurt():
    tz = ZoneInfo("Europe/Berlin")
    local_dt = datetime(2024, 5, 9, 0, 0, tzinfo=tz)

    ts = to_utc_midnight(local_dt)

    # 2024-05-09 00:00 CEST = 2024-05-08 22:00 UTC → snapped to 2024-05-09 00:00 UTC
    assert ts == int(datetime(2024, 5, 9, 0, 0, tzinfo=UTC).timestamp())


def test_to_utc_midnight_idempotent_for_utc():
    local_dt = datetime(2024, 5, 9, 12, 34, tzinfo=UTC)

    ts = to_utc_midnight(local_dt)

    # Should snap to 2024-05-09 00:00 UTC
    assert ts == int(datetime(2024, 5, 9, 0, 0, tzinfo=UTC).timestamp())


def test_to_utc_midnight_australia():
    tz = ZoneInfo("Australia/Sydney")
    # Arbitrary date; Sydney is ahead of UTC
    local_dt = datetime(2024, 5, 9, 0, 0, tzinfo=tz)

    ts = to_utc_midnight(local_dt)

    # Local midnight in Sydney corresponds to previous UTC date
    expected = int(datetime(2024, 5, 9, 0, 0, tzinfo=UTC).timestamp())
    assert ts == expected


def test_to_utc_midnight_hawaii():
    tz = ZoneInfo("Pacific/Honolulu")
    # Arbitrary date; Sydney is ahead of UTC
    local_dt = datetime(2024, 5, 9, 0, 0, tzinfo=tz)

    ts = to_utc_midnight(local_dt)

    # Local midnight in Sydney corresponds to previous UTC date
    expected = int(datetime(2024, 5, 10, 0, 0, tzinfo=UTC).timestamp())
    assert ts == expected
