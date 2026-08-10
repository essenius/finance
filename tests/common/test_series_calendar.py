# Copyright 2026 Rik Essenius
# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.
# File: tests/common/test_series_calendar.py

from datetime import UTC, date, datetime, time, timedelta
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


def test_snap_forward_interval_and_back():

    interval = timedelta(minutes=15)
    calendar = make_calendar(interval=interval)
    assert calendar.get_publication_offset() == interval
    assert not calendar.is_overnight()
    assert not calendar.is_daily()

    base = datetime(2026, 7, 10, 9, tzinfo=UTC)
    assert calendar.snap_forward_interval(base) == base, "snap forward did not change"
    assert calendar.snap_back_interval(base) == base, "snap back did not change"
    above_base = base + timedelta(microseconds=1)
    assert calendar.snap_forward_interval(above_base) == datetime(2026, 7, 10, 9, 15, tzinfo=UTC), (
        "snap forward moves up"
    )
    under_next = base + calendar.interval - timedelta(microseconds=1)
    assert calendar.snap_back_interval(under_next) == base, "snap back moves down"


# ------------------------------------------------------------
# Weekly and daily limits
# ------------------------------------------------------------


def test_weekly_limits_days_normal_series():
    dubai = ZoneInfo("Asia/Dubai")
    calendar = make_calendar(
        timezone=dubai,
        market_open=time(9, 0),
        market_close=time(16, 0),
        week_start=5,  # sat
        week_end=2,  # wed
    )

    # Friday is in the weekend, so start/end must be before
    start, end = calendar.weekly_trading_window_days(date(2026, 7, 10))
    assert start == date(2026, 7, 4)
    assert end == date(2026, 7, 8)

    # Sunday is not in the weekend, so start must be before and end after
    start, end = calendar.weekly_trading_window_days(date(2026, 7, 12))
    assert start == date(2026, 7, 11)
    assert end == date(2026, 7, 15)


def test_weekly_limits_days_overnight_series():
    sydney = ZoneInfo("Australia/Sydney")
    calendar = make_calendar(
        timezone=sydney,
        market_open=time(14, 0),
        market_close=time(4, 0),
    )

    # Saturday
    start, end = calendar.weekly_trading_window_days(date(2026, 7, 11))
    # Start is Monday, as that is the trading day (even though it starts Sunday)
    assert start == date(2026, 7, 6)
    assert end == date(2026, 7, 10)

    # Monday
    start, end = calendar.weekly_trading_window_days(date(2026, 7, 6))
    assert start == date(2026, 7, 6)
    assert end == date(2026, 7, 10)

    # Sunday
    start, end = calendar.weekly_trading_window_days(date(2026, 7, 12))
    assert start == date(2026, 7, 6)
    assert end == date(2026, 7, 10)


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
    start, end = calendar.weekly_trading_window(datetime(2026, 7, 10, 15, tzinfo=dubai))
    assert start == datetime(2026, 7, 4, 9, tzinfo=dubai)
    assert end == datetime(2026, 7, 8, 16, tzinfo=dubai)

    # Sunday is not in the weekend, so start must be before and end after
    start, end = calendar.weekly_trading_window(datetime(2026, 7, 12, 15, tzinfo=dubai))
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
    start, end = calendar.weekly_trading_window(datetime(2026, 7, 10, 6, tzinfo=sydney))
    # Start is Sunday, not Monday
    assert start == datetime(2026, 7, 5, 14, tzinfo=sydney)
    assert end == datetime(2026, 7, 10, 4, tzinfo=sydney)

    # Monday during trading hours
    start, end = calendar.weekly_trading_window(datetime(2026, 7, 6, 15, tzinfo=sydney))
    assert start == datetime(2026, 7, 5, 14, tzinfo=sydney)
    assert end == datetime(2026, 7, 10, 4, tzinfo=sydney)

    # Sunday before market open
    start, end = calendar.weekly_trading_window(datetime(2026, 7, 12, 12, tzinfo=sydney))
    assert start == datetime(2026, 7, 5, 14, tzinfo=sydney)
    assert end == datetime(2026, 7, 10, 4, tzinfo=sydney)


def test_daily_limits_normal_series():
    hawaii = ZoneInfo("Pacific/Honolulu")
    calendar = make_calendar(
        timezone=hawaii,
        market_open=time(9, 0),
        market_close=time(15, 0),
    )
    start, end = calendar.daily_trading_window_snapped(datetime(2026, 7, 9, 12, tzinfo=hawaii))
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
    start, end = calendar.daily_trading_window_snapped(datetime(2026, 7, 6, 12, tzinfo=hawaii))
    assert start == datetime(2026, 7, 5, 17, tzinfo=hawaii)
    assert end == datetime(2026, 7, 6, 16, tzinfo=hawaii)

    # after opening
    start, end = calendar.daily_trading_window_snapped(datetime(2026, 7, 6, 18, tzinfo=hawaii))
    assert start == datetime(2026, 7, 6, 17, tzinfo=hawaii)
    assert end == datetime(2026, 7, 7, 16, tzinfo=hawaii)


# ------------------------------------------------------------
# snap_forward_identity (intraday and daily)
# ------------------------------------------------------------


def test_snap_forward_identity_intraday_normal():
    calendar = make_calendar(
        timezone=ZoneInfo("Europe/Amsterdam"),
        market_open=time(9, 0),
        market_close=time(17, 30),
        interval=timedelta(minutes=15),
    )

    start_of_week = datetime(2026, 7, 13, 7, tzinfo=UTC)
    start_of_week_local = datetime(2026, 7, 13, 9, tzinfo=ZoneInfo("Europe/Amsterdam"))
    friday_after_hours = datetime(2026, 7, 10, 23, 55, tzinfo=UTC)

    next_id = calendar.snap_forward_identity(friday_after_hours)
    assert next_id.store_label() == start_of_week
    assert next_id.publish_label() == start_of_week_local

    monday_before_hours = datetime(2026, 7, 13, 6, tzinfo=UTC)
    next_id = calendar.snap_forward_identity(monday_before_hours)
    assert next_id.store_label() == start_of_week

    tuesday_before_hours = datetime(2026, 7, 14, 6, tzinfo=UTC)
    next_id = calendar.snap_forward_identity(tuesday_before_hours)
    assert next_id.store_label() == datetime(2026, 7, 14, 7, tzinfo=UTC)

    wednesday_after_hours = datetime(2026, 7, 15, 16, tzinfo=UTC)
    next_id = calendar.snap_forward_identity(wednesday_after_hours)
    assert next_id.store_label() == datetime(2026, 7, 16, 7, tzinfo=UTC)

    thursday_trading = datetime(2026, 7, 16, 12, 3, tzinfo=UTC)
    next_id = calendar.snap_forward_identity(thursday_trading)
    assert next_id.store_label() == datetime(2026, 7, 16, 12, 15, tzinfo=UTC)


def test_snap_forward_identity_daily_normal():
    calendar = make_calendar(
        timezone=ZoneInfo("Europe/Amsterdam"),
        market_open=time(9, 0),
        market_close=time(17, 30),
        interval=timedelta(days=1),
    )

    start_of_week_utc = datetime(2026, 7, 13, tzinfo=UTC)
    start_of_week_local = datetime(2026, 7, 13, tzinfo=ZoneInfo("Europe/Amsterdam"))
    friday_after_hours = datetime(2026, 7, 10, 23, 55, tzinfo=UTC)

    next_id = calendar.snap_forward_identity(friday_after_hours)
    assert next_id.store_label() == start_of_week_utc
    assert next_id.publish_label() == start_of_week_local

    monday_before_hours = datetime(2026, 7, 13, 6, tzinfo=UTC)
    next_id = calendar.snap_forward_identity(monday_before_hours)
    assert next_id.store_label() == start_of_week_utc

    tuesday_before_hours = datetime(2026, 7, 14, 6, tzinfo=UTC)
    next_id = calendar.snap_forward_identity(tuesday_before_hours)
    assert next_id.store_label() == datetime(2026, 7, 14, tzinfo=UTC)

    wednesday_after_hours = datetime(2026, 7, 15, 16, tzinfo=UTC)
    next_id = calendar.snap_forward_identity(wednesday_after_hours)
    assert next_id.store_label() == datetime(2026, 7, 16, tzinfo=UTC)

    thursday_trading = datetime(2026, 7, 16, 12, 3, tzinfo=UTC)
    next_id = calendar.snap_forward_identity(thursday_trading)
    assert next_id.store_label() == datetime(2026, 7, 16, tzinfo=UTC)


def test_snap_forward_identity_intraday_overnight():
    calendar = make_calendar(
        timezone=ZoneInfo("Europe/Amsterdam"),
        market_open=time(17, 0),
        market_close=time(4, 0),
    )

    weekend_started = datetime(2026, 7, 10, 2, tzinfo=UTC)
    next_id = calendar.snap_forward_identity(weekend_started)
    assert next_id.store_label() == datetime(2026, 7, 12, 15, tzinfo=UTC), (
        "next is market open on Sunday (belongs to Monday trading)"
    )

    inside = datetime(2026, 7, 10, 1, 45, tzinfo=UTC)
    next_id = calendar.snap_forward_identity(inside)
    assert next_id.store_label() == inside, "next is the point itself"

    # in close time, so should move to next open time
    monday_after_close = datetime(2026, 7, 13, 3, tzinfo=UTC)
    next_id = calendar.snap_forward_identity(monday_after_close)
    assert next_id.store_label() == datetime(2026, 7, 13, 15, 0, tzinfo=UTC), "next is market open on Monday"


def test_snap_forward_identity_daily_overnight():
    calendar = make_calendar(
        timezone=ZoneInfo("Europe/Amsterdam"),
        market_open=time(17, 0),
        market_close=time(4, 0),
        interval=timedelta(days=1),
    )

    # tests for helpers while we have a suitable calendar
    assert calendar.get_publication_offset() == timedelta(hours=4), "4 hours offset from publication label"
    assert calendar.is_overnight()
    assert calendar.is_daily()

    weekend_started = datetime(2026, 7, 10, 2, 1, tzinfo=UTC)
    next_id = calendar.snap_forward_identity(weekend_started)
    assert next_id.store_label() == datetime(2026, 7, 13, tzinfo=UTC), (
        "Market is open on Sunday, but belongs to Monday trading"
    )

    inside = datetime(2026, 7, 10, 1, 45, tzinfo=UTC)
    next_id = calendar.snap_forward_identity(inside)
    assert next_id.store_label() == datetime(2026, 7, 10, tzinfo=UTC), "next label is midnight UTC today"

    # in close time, so should move to next open time
    monday_after_close = datetime(2026, 7, 13, 3, tzinfo=UTC)
    next_id = calendar.snap_forward_identity(monday_after_close)
    assert next_id.store_label() == datetime(2026, 7, 14, tzinfo=UTC), "next label is Tuesday, as after Monday close"


# ------------------------------------------------------------
# snap_back_identity (intraday and daily)
# ------------------------------------------------------------


def test_snap_back_identity_intraday_normal():
    calendar = make_calendar(
        timezone=ZoneInfo("Europe/Amsterdam"),
        market_open=time(9, 0),
        market_close=time(17, 0),
    )

    tuesday_before_hours = datetime(2026, 7, 14, 4, 0, tzinfo=UTC)
    last_id = calendar.snap_back_identity(tuesday_before_hours)
    assert last_id.store_label() == datetime(2026, 7, 13, 15, tzinfo=UTC), "snapped is market close on Monday"

    monday_before_hours = datetime(2026, 7, 13, 4, 0, tzinfo=UTC)
    last_id = calendar.snap_back_identity(monday_before_hours)
    assert last_id.store_label() == datetime(2026, 7, 10, 15, tzinfo=UTC), "snapped is market close on Friday"


def test_snap_back_identity_intraday_overnight():
    calendar = make_calendar(
        timezone=ZoneInfo("Europe/Amsterdam"),
        market_open=time(17, 0),
        market_close=time(4, 0),
    )

    friday_after_hours = datetime(2026, 7, 10, 12, 0, tzinfo=UTC)
    # this is Friday 14:00 local, which is in the weekend window
    last_id = calendar.snap_back_identity(friday_after_hours)

    # so previous should be 4am on Friday, i.e. 2am UTC
    assert last_id.store_label() == datetime(2026, 7, 10, 2, tzinfo=UTC)

    # midnight on Friday is in the trading window
    inside = datetime(2026, 7, 10, tzinfo=UTC)
    last_id = calendar.snap_back_identity(inside)
    assert last_id.store_label() == inside

    closed = datetime(2026, 7, 8, 12, tzinfo=UTC)
    last_id = calendar.snap_back_identity(closed)
    assert last_id.store_label() == datetime(2026, 7, 8, 2, tzinfo=UTC)

    monday_before_hours = datetime(2026, 7, 13, 14, 0, tzinfo=UTC)
    last_id = calendar.snap_back_identity(monday_before_hours)
    # overnight starts on Sunday and runs into Monday
    assert last_id.store_label() == datetime(2026, 7, 13, 2, tzinfo=UTC)


def test_snap_back_identity_daily_normal():
    dubai = ZoneInfo("Asia/Dubai")
    calendar = make_calendar(
        timezone=dubai,
        market_open=time(9, 0),
        market_close=time(16, 0),
        week_start=5,  # sat
        week_end=2,  # wed
        interval=timedelta(days=1),
    )

    tuesday_before_hours = datetime(2026, 7, 14, 4, 0, tzinfo=dubai)
    last_id = calendar.snap_back_identity(tuesday_before_hours)
    assert last_id.store_label() == datetime(2026, 7, 13, tzinfo=UTC), "last market day was Monday"

    friday = datetime(2026, 7, 17, 12, 0, tzinfo=dubai)
    # in the weekend window
    last_id = calendar.snap_back_identity(friday)

    # so previous should be Wednesday
    assert last_id.store_label() == datetime(2026, 7, 15, tzinfo=UTC)


def test_snap_back_identity_daily_overnight():
    calendar = make_calendar(
        timezone=ZoneInfo("Europe/Amsterdam"),
        market_open=time(17, 0),
        market_close=time(4, 0),
        interval=timedelta(days=1),
    )

    friday_after_hours = datetime(2026, 7, 10, 12, 0, tzinfo=UTC)
    # this is Friday 14:00 local, which is in the weekend window
    last_id = calendar.snap_back_identity(friday_after_hours)

    # so previous should be Friday
    assert last_id.store_label() == datetime(2026, 7, 10, tzinfo=UTC)

    # midnight on Friday is in the trading window
    inside = datetime(2026, 7, 10, tzinfo=UTC)
    last_id = calendar.snap_back_identity(inside)
    assert last_id.store_label() == inside

    closed = datetime(2026, 7, 8, 12, tzinfo=UTC)
    last_id = calendar.snap_back_identity(closed)
    assert last_id.store_label() == datetime(2026, 7, 8, tzinfo=UTC)

    monday_before_hours = datetime(2026, 7, 13, 14, 0, tzinfo=UTC)
    last_id = calendar.snap_back_identity(monday_before_hours)
    # Monday finished, so the last trading day was Monday
    assert last_id.store_label() == datetime(2026, 7, 13, tzinfo=UTC)

    sunday_trading = datetime(2026, 7, 12, 18, tzinfo=UTC)
    last_id = calendar.snap_back_identity(sunday_trading)
    # Sunday trades in overnight series belong to Monday
    assert last_id.store_label() == datetime(2026, 7, 13, tzinfo=UTC)

    sunday_before_hours = datetime(2026, 7, 12, 1, tzinfo=UTC)
    last_id = calendar.snap_back_identity(sunday_before_hours)
    # Previous was Friday
    assert last_id.store_label() == datetime(2026, 7, 10, tzinfo=UTC)
