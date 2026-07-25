# Copyright 2026 Rik Essenius
# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.
# File: tests/common/test_series_calendar.py

from datetime import UTC, datetime, time, timedelta
from zoneinfo import ZoneInfo

from finance.common.series_calendar import SeriesCalendar


def make_calendar(
    *,
    interval=timedelta(minutes=5),
    timezone=UTC,
    market_open=time.min,
    market_close=time.max,
    week_start=0,  # Monday
    week_end=4,  # Friday
    publication_offset=None,
):
    return SeriesCalendar(
        interval=interval,
        timezone=timezone,
        market_open=market_open,
        market_close=market_close,
        week_start=week_start,
        week_end=week_end,
        publication_offset=publication_offset,
    )


def test_from_series(make_series):
    series = make_series(asset=None, timezone=ZoneInfo("America/Chicago"))
    calendar = SeriesCalendar.from_series(series)
    assert calendar.interval == timedelta(minutes=10)
    assert calendar.timezone.key == "America/Chicago"
    assert calendar.market_open == time.min
    assert calendar.market_close == time.max
    assert calendar.week_start == 0
    assert calendar.week_end == 4
    assert calendar.publication_offset is None


# ------------------------------------------------------------
# Snap
# ------------------------------------------------------------


def test_snap_to_next_and_previous():

    calendar = make_calendar(interval=timedelta(minutes=15))
    base = datetime(2026, 7, 10, 9, tzinfo=UTC)
    assert calendar.snap_to_next(base) == base, "next equals"
    above_base = base + timedelta(microseconds=1)
    assert calendar.snap_to_next(above_base) == datetime(2026, 7, 10, 9, 15, tzinfo=UTC), "next above"
    under_next = base + calendar.interval - timedelta(microseconds=1)
    assert calendar.snap_to_previous(under_next) == base, "previous above"


# ------------------------------------------------------------
# Weekly and daily limits
# ------------------------------------------------------------


def test_weekly_limits_normal_series():
    dubai = ZoneInfo("Asia/Dubai")
    calendar = make_calendar(
        timezone=dubai,
        market_open=time(9, 0),
        market_close=time(16, 0),
        week_start=5,  # sat
        week_end=2,  # wed
    )

    # Friday is in the weekend, so start/end must be before
    start, end = calendar.weekly_limits(datetime(2026, 7, 10, 15, tzinfo=dubai))
    assert start == datetime(2026, 7, 4, 9, tzinfo=dubai)
    assert end == datetime(2026, 7, 8, 16, tzinfo=dubai)

    # Sunday is not in the weekend, so start must be before and end after
    start, end = calendar.weekly_limits(datetime(2026, 7, 12, 15, tzinfo=dubai))
    assert start == datetime(2026, 7, 11, 9, tzinfo=dubai)
    assert end == datetime(2026, 7, 15, 16, tzinfo=dubai)


def test_weekly_limits_overnight_series():
    sydney = ZoneInfo("Australia/Sydney")
    calendar = make_calendar(
        timezone=sydney,
        market_open=time(14, 0),
        market_close=time(4, 0),
    )

    # Friday after market close
    start, end = calendar.weekly_limits(datetime(2026, 7, 10, 6, tzinfo=sydney))
    # Start is Sunday, not Monday
    assert start == datetime(2026, 7, 5, 14, tzinfo=sydney)
    assert end == datetime(2026, 7, 10, 4, tzinfo=sydney)

    # Monday during trading hours
    start, end = calendar.weekly_limits(datetime(2026, 7, 6, 15, tzinfo=sydney))
    assert start == datetime(2026, 7, 5, 14, tzinfo=sydney)
    assert end == datetime(2026, 7, 10, 4, tzinfo=sydney)

    # Sunday before market open
    start, end = calendar.weekly_limits(datetime(2026, 7, 12, 12, tzinfo=sydney))
    assert start == datetime(2026, 7, 5, 14, tzinfo=sydney)
    assert end == datetime(2026, 7, 10, 4, tzinfo=sydney)


def test_daily_limits_normal_series():
    hawaii = ZoneInfo("Pacific/Honolulu")
    calendar = make_calendar(
        timezone=hawaii,
        market_open=time(9, 0),
        market_close=time(15, 0),
    )
    start, end = calendar.daily_limits(datetime(2026, 7, 9, 12, tzinfo=hawaii))
    assert start == datetime(2026, 7, 9, 9, tzinfo=hawaii)
    assert end == datetime(2026, 7, 9, 15, tzinfo=hawaii)


def test_daily_limits_overnight_series():
    hawaii = ZoneInfo("Pacific/Honolulu")
    calendar = make_calendar(
        timezone=hawaii,
        market_open=time(17, 0),
        market_close=time(16, 0),
    )

    # before opening
    start, end = calendar.daily_limits(datetime(2026, 7, 6, 12, tzinfo=hawaii))
    assert start == datetime(2026, 7, 5, 17, tzinfo=hawaii)
    assert end == datetime(2026, 7, 6, 16, tzinfo=hawaii)

    # after opening
    start, end = calendar.daily_limits(datetime(2026, 7, 6, 18, tzinfo=hawaii))
    assert start == datetime(2026, 7, 6, 17, tzinfo=hawaii)
    assert end == datetime(2026, 7, 7, 16, tzinfo=hawaii)


# ------------------------------------------------------------
# Next and previous publication time
# ------------------------------------------------------------


def test_next_publication_time_day_session():
    calendar = make_calendar(
        timezone=ZoneInfo("Europe/Amsterdam"),
        market_open=time(9, 0),
        market_close=time(17, 30),
        interval=timedelta(minutes=15),
    )

    start_of_week = datetime(2026, 7, 13, 7, tzinfo=UTC)
    friday_after_hours = datetime(2026, 7, 10, 23, 55, tzinfo=UTC)
    next_pub = calendar.next_label_time(friday_after_hours)
    assert next_pub == start_of_week

    monday_before_hours = datetime(2026, 7, 13, 6, tzinfo=UTC)
    next_pub = calendar.next_label_time(monday_before_hours)
    assert next_pub == start_of_week

    tuesday_before_hours = datetime(2026, 7, 14, 6, tzinfo=UTC)
    next_pub = calendar.next_label_time(tuesday_before_hours)
    assert next_pub == datetime(2026, 7, 14, 7, tzinfo=UTC)

    wednesday_after_hours = datetime(2026, 7, 15, 16, tzinfo=UTC)
    next_pub = calendar.next_label_time(wednesday_after_hours)
    assert next_pub == datetime(2026, 7, 16, 7, tzinfo=UTC)

    thursday_trading = datetime(2026, 7, 16, 12, 3, tzinfo=UTC)
    next_pub = calendar.next_label_time(thursday_trading)
    assert next_pub == datetime(2026, 7, 16, 12, 15, tzinfo=UTC)


def test_next_publication_time_overnight_session():
    calendar = make_calendar(
        timezone=ZoneInfo("Europe/Amsterdam"),
        market_open=time(17, 0),
        market_close=time(4, 0),
    )

    weekend_started = datetime(2026, 7, 10, 2, 0, tzinfo=UTC)
    next_pub = calendar.next_label_time(weekend_started)
    assert next_pub == datetime(2026, 7, 12, 15, 0, tzinfo=UTC), "next is market open on Sunday"

    inside = datetime(2026, 7, 10, 1, 45, tzinfo=UTC)
    next_pub = calendar.next_label_time(inside)
    assert next_pub == inside, "next is the point itself"

    # in close time, so should move to next open time
    monday_after_close = datetime(2026, 7, 13, 3, 0, tzinfo=UTC)
    next_pub = calendar.next_label_time(monday_after_close)
    assert next_pub == datetime(2026, 7, 13, 15, 0, tzinfo=UTC), "next is market open on Monday"


def test_previous_publication_time_normal_session():
    calendar = make_calendar(
        timezone=ZoneInfo("Europe/Amsterdam"),
        market_open=time(9, 0),
        market_close=time(17, 0),
    )

    tuesday_before_hours = datetime(2026, 7, 14, 4, 0, tzinfo=UTC)
    last_pub = calendar.previous_label_time(tuesday_before_hours)
    assert last_pub == datetime(2026, 7, 13, 15, 0, tzinfo=UTC), "next is market close on Monday"


def test_previous_publication_time_overnight_session():
    calendar = make_calendar(
        timezone=ZoneInfo("Europe/Amsterdam"),
        market_open=time(17, 0),
        market_close=time(4, 0),
    )

    friday_after_hours = datetime(2026, 7, 10, 12, 0, tzinfo=UTC)
    # this is Friday 14:00 local, which is in the weekend window
    last_pub = calendar.previous_label_time(friday_after_hours)

    # so previous should be 4am on Friday, i.e. 2am UTC
    assert last_pub == datetime(2026, 7, 10, 2, 0, tzinfo=UTC)

    # midnight on Friday is in the trading window
    inside = datetime(2026, 7, 10, tzinfo=UTC)
    last_pub = calendar.previous_label_time(inside)
    assert last_pub == inside

    closed = datetime(2026, 7, 8, 12, 0, tzinfo=UTC)
    last_pub = calendar.previous_label_time(closed)
    assert last_pub == datetime(2026, 7, 8, 2, 0, tzinfo=UTC)

    monday_before_hours = datetime(2026, 7, 13, 14, 0, tzinfo=UTC)
    last_pub = calendar.previous_label_time(monday_before_hours)
    # overnight starts on Sunday and runs into Monday
    assert last_pub == datetime(2026, 7, 13, 2, 0, tzinfo=UTC)


def test_last_publication_before():
    tokyo = ZoneInfo("Asia/Tokyo")
    calendar = make_calendar(
        timezone=tokyo,
        market_open=time(9, 0),
        market_close=time(16, 0),
    )

    start_of_week = datetime(2026, 7, 13, 0, 0, tzinfo=UTC)
    last_pub = calendar.previous_label_time(start_of_week)
    assert start_of_week == last_pub
    last_pub_before = calendar.last_label_time_before(start_of_week)
    assert last_pub_before == datetime(2026, 7, 10, 7, 0, tzinfo=UTC)
