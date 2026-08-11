# Copyright 2026 Rik Essenius
# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.
# File: src/finance/common/series_calendar.py

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from finance.common.candle_identity import CandleIdentity

from ..common.model import Series
from ..common.time_utils import parse_duration, parse_weekday, snap_to

ONE_DAY = timedelta(days=1)
ONE_WEEK = timedelta(weeks=1)
ONE_MICROSECOND = timedelta(microseconds=1)


@dataclass
class SeriesCalendar:
    interval: timedelta
    timezone: ZoneInfo
    market_open: time
    market_close: time
    week_start: int
    week_end: int
    publication_offset: timedelta | None
    _offset: timedelta | None = None

    @classmethod
    def from_series(cls, series: Series) -> SeriesCalendar:
        return cls(
            interval=series.interval_delta(),
            timezone=series.timezone,
            market_open=series.market_open,
            market_close=series.market_close,
            week_start=parse_weekday(series.week_start),
            week_end=parse_weekday(series.week_end),
            publication_offset=parse_duration(series.publication_offset, f"interval for {series.name}"),
        )

    def is_overnight(self) -> bool:
        return self.market_open > self.market_close

    def is_daily(self) -> bool:
        return self.interval >= ONE_DAY

    def get_publication_offset(self) -> timedelta:
        if self.publication_offset is not None:
            return self.publication_offset

        if self.is_daily() and self.is_overnight():
            return datetime.combine(date.min, self.market_close, tzinfo=UTC) - datetime.min.replace(tzinfo=UTC)

        return self.interval

    def utc_to_local(self, ts: datetime) -> datetime:
        return ts.astimezone(self.timezone)

    def combine_local(self, local_day: date, local_time: time) -> datetime:
        return datetime.combine(local_day, local_time, tzinfo=self.timezone)

    def make_candle_identity(self, label: datetime) -> CandleIdentity:
        return CandleIdentity(value=label, is_daily=self.is_daily(), interval=self.interval)

    def snap_back_interval(self, ts: datetime) -> datetime:
        # snap to already snaps to previous
        return self.utc_to_local(snap_to(ts, self.interval))

    def snap_forward_interval(self, ts: datetime) -> datetime:
        snapped = self.snap_back_interval(ts)
        if snapped < ts:
            snapped += self.interval
        return snapped

    def weekly_trading_window_days(self, local: date) -> tuple[date, date]:
        ## determine week start before the local point (% delivers positive)
        start_delta = timedelta(days=(local.weekday() - self.week_start) % 7)
        open_day = local - start_delta
        # determine the week end after the week start
        end_delta = timedelta(days=(self.week_end - self.week_start) % 7)
        close_day = open_day + end_delta
        return open_day, close_day

    def weekly_trading_window(self, local: datetime) -> tuple[datetime, datetime]:
        open_day, close_day = self.weekly_trading_window_days(local.date())
        open = self.combine_local(open_day, self.market_open)
        close = self.combine_local(close_day, self.market_close)

        # correct weekly window for overnight series (starts the previous day)
        if self.is_overnight():
            open -= ONE_DAY
        return (self.snap_forward_interval(open), self.snap_back_interval(close))

    def daily_trading_window(self, local: datetime) -> tuple[datetime, datetime]:
        local_date = local.date()

        open = self.combine_local(local_date, self.market_open)
        close = self.combine_local(local_date, self.market_close)
        # correct SOD/EOD in case of overnight series
        if self.is_overnight():
            if local < open:
                open -= ONE_DAY
            else:
                close += ONE_DAY
        # take the first point in the interval on or after open and the last one on or before close
        return open, close

    def daily_trading_window_snapped(self, local: datetime) -> tuple[datetime, datetime]:
        open, close = self.daily_trading_window(local)
        if self.market_close == time.max:
            close += ONE_MICROSECOND  # time.max is one microsecond from the next day
        return (self.snap_forward_interval(open), self.snap_back_interval(close))

    def snap_back_trading_week(self, local: date) -> date:
        _, eow = self.weekly_trading_window_days(local)
        if local >= eow:
            return eow
        return local

    def snap_forward_trading_week(self, local: date) -> date:
        sow, eow = self.weekly_trading_window_days(local)
        if local > eow:
            return sow + ONE_WEEK
        return local

    def snap_back_intraday_interval(self, local: datetime) -> datetime:
        sow, eow = self.weekly_trading_window(local)
        if local >= eow:
            return eow
        if local < sow:  # can happen before market open on start of week day
            return eow - ONE_WEEK
        sod, eod = self.daily_trading_window_snapped(local)
        if local > eod:
            return eod
        if local < sod:
            return eod - ONE_DAY
        return local

    def snap_forward_intraday_interval(self, local: datetime) -> datetime:
        sow, eow = self.weekly_trading_window(local)
        if local < sow:
            return sow
        if local >= eow:
            return sow + ONE_WEEK
        sod, eod = self.daily_trading_window_snapped(local)
        if local < sod:
            return sod
        if local > eod:
            return sod + ONE_DAY
        return local

    def snap_back_trading_day(self, local: datetime) -> date:
        open, close = self.daily_trading_window(local)
        day = close.date()
        if local < open:
            day -= ONE_DAY
        return self.snap_back_trading_week(day)

    def snap_forward_trading_day(self, local: datetime) -> date:
        _, close = self.daily_trading_window(local)
        day = close.date()
        # close was already snapped to interval here. That is what causes the mismatch
        if local > close:
            day += ONE_DAY
        return self.snap_forward_trading_week(day)

    # we use the publish label because that holds the local timezone. Store label can be deduced from that
    def snap_back_trading_day_label(self, local: datetime) -> datetime:
        day = self.snap_back_trading_day(local)
        last_trading_day = self.snap_back_trading_week(day)
        return datetime.combine(last_trading_day, time.min, tzinfo=local.tzinfo)

    def snap_forward_trading_day_label(self, local: datetime) -> datetime:
        day = self.snap_forward_trading_day(local)
        next_trading_day = self.snap_forward_trading_week(day)
        return datetime.combine(next_trading_day, time.min, tzinfo=local.tzinfo)

    def snap_back_identity(self, moment_utc: datetime) -> CandleIdentity:
        local = self.utc_to_local(moment_utc)

        if self.is_daily():
            trading_day_label = self.snap_back_trading_day_label(local)
            return self.make_candle_identity(trading_day_label)

        value = self.snap_back_interval(local)
        candle_label = self.snap_back_intraday_interval(value)
        return self.make_candle_identity(candle_label)

    def snap_forward_identity(self, moment_utc: datetime) -> CandleIdentity:
        local = self.utc_to_local(moment_utc)

        if self.is_daily():
            trading_day_label = self.snap_forward_trading_day_label(local)
            return self.make_candle_identity(trading_day_label)

        value = self.snap_forward_interval(local)
        candle_label = self.snap_forward_intraday_interval(value)
        return self.make_candle_identity(candle_label)

    def snap_back_on_publish_time(self, local: datetime, id: CandleIdentity):
        if local < id.publish_label() + self.get_publication_offset():
            old_label = id.publish_label()  # in local timezone
            new_label = self.snap_back_trading_week(old_label - self.interval)
            return replace(id, value=new_label)
        return id

    def last_identity_before(self, moment_utc: datetime) -> CandleIdentity:
        return self.snap_back_identity(moment_utc - ONE_MICROSECOND)
