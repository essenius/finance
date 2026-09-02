# Copyright 2026 Rik Essenius
# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.
# File: src/finance/common/series_calendar.py

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from ..common.asset_metadata import AssetMetadata
from ..common.candle_identity import CandleIdentity
from ..common.time_utils import UTC, parse_weekday, snap_to

ONE_DAY = timedelta(days=1)
ONE_WEEK = timedelta(weeks=1)
ONE_MICROSECOND = timedelta(microseconds=1)

MONDAY = 0
FRIDAY = 4


def default_if_none[T](value: T | None, default: T) -> T:
    return default if value is None else value


@dataclass
class SeriesCalendar:
    timezone: ZoneInfo
    market_open: time
    market_close: time
    week_start: int
    week_end: int
    interval: timedelta
    publication_offset: timedelta | None = None
    first_available_date: date | None = None

    # _offset: timedelta | None = None

    @classmethod
    def create(cls, interval: timedelta, publication_offset: timedelta | None, meta: AssetMetadata) -> SeriesCalendar:
        return cls(
            # the defaults are primarily useful for the first fetch, when we might not have all metadata yet.
            # it may result in a slightly inaccurate window, which is corrected the next run.
            timezone=default_if_none(meta.timezone, UTC),
            market_open=default_if_none(meta.market_open, time.min),
            market_close=default_if_none(meta.market_close, time.max),
            week_start=default_if_none(parse_weekday(meta.week_start), MONDAY),
            week_end=default_if_none(parse_weekday(meta.week_end), FRIDAY),
            interval=interval,
            publication_offset=publication_offset,
            first_available_date=meta.first_available_date,
        )

    def first_trade_time(self) -> datetime | None:
        if self.first_available_date is None:
            return None
        return datetime.combine(self.first_available_date, time.min, self.timezone)

    def last_identity_before(self, moment_utc: datetime) -> CandleIdentity:
        return self.snap_back_identity(moment_utc - ONE_MICROSECOND)

    def snap_back_identity(self, moment_utc: datetime) -> CandleIdentity:
        local = self._utc_to_local(moment_utc)

        if self._is_daily():
            trading_day_label = self._snap_back_trading_day_label(local)
            return self._make_candle_identity(trading_day_label)

        value = self.snap_back_interval(local)
        candle_label = self._snap_back_intraday_interval(value)
        return self._make_candle_identity(candle_label)

    def snap_back_interval(self, ts: datetime) -> datetime:
        # snap to already snaps to previous
        return self._utc_to_local(snap_to(ts, self.interval))

    def snap_back_on_publish_time(self, local: datetime, id: CandleIdentity):
        if local < id.publish_label() + self._get_publication_offset():
            old_label = id.publish_label()  # in local timezone
            new_label = self._snap_back_trading_week(old_label - self.interval)
            return replace(id, value=new_label)
        return id

    def snap_forward_identity(self, moment_utc: datetime) -> CandleIdentity:
        local = self._utc_to_local(moment_utc)

        if self._is_daily():
            trading_day_label = self._snap_forward_trading_day_label(local)
            return self._make_candle_identity(trading_day_label)

        value = self.snap_forward_interval(local)
        candle_label = self._snap_forward_intraday_interval(value)
        return self._make_candle_identity(candle_label)

    def snap_forward_interval(self, ts: datetime) -> datetime:
        snapped = self.snap_back_interval(ts)
        if snapped < ts:
            snapped += self.interval
        return snapped

    # ----------------
    # Private methods
    # ----------------

    def _combine_local(self, local_day: date, local_time: time) -> datetime:
        return datetime.combine(local_day, local_time, tzinfo=self.timezone)

    def _daily_trading_window(self, local: datetime) -> tuple[datetime, datetime]:
        local_date = local.date()

        open = self._combine_local(local_date, self.market_open)
        close = self._combine_local(local_date, self.market_close)
        # correct SOD/EOD in case of overnight series
        if self._is_overnight():
            if local < open:
                open -= ONE_DAY
            else:
                close += ONE_DAY
        # take the first point in the interval on or after open and the last one on or before close
        return open, close

    def _daily_trading_window_snapped(self, local: datetime) -> tuple[datetime, datetime]:
        open, close = self._daily_trading_window(local)
        if self.market_close == time.max:
            close += ONE_MICROSECOND  # time.max is one microsecond from the next day
        return (self.snap_forward_interval(open), self.snap_back_interval(close))

    def _get_publication_offset(self) -> timedelta:
        if self.publication_offset is not None:
            return self.publication_offset

        if self._is_daily() and self._is_overnight():
            return datetime.combine(date.min, self.market_close, tzinfo=UTC) - datetime.min.replace(tzinfo=UTC)

        return self.interval

    def _is_daily(self) -> bool:
        return self.interval >= ONE_DAY

    def _is_overnight(self) -> bool:
        return self.market_open > self.market_close

    def _make_candle_identity(self, label: datetime) -> CandleIdentity:
        return CandleIdentity(value=label, is_daily=self._is_daily(), interval=self.interval)

    def _snap_back_intraday_interval(self, local: datetime) -> datetime:
        sow, eow = self._weekly_trading_window(local)
        if local >= eow:
            return eow
        if local < sow:  # can happen before market open on start of week day
            return eow - ONE_WEEK
        sod, eod = self._daily_trading_window_snapped(local)
        if local > eod:
            return eod
        if local < sod:
            return eod - ONE_DAY
        return local

    def _snap_back_trading_day(self, local: datetime) -> date:
        open, close = self._daily_trading_window(local)
        day = close.date()
        if local < open:
            day -= ONE_DAY
        return self._snap_back_trading_week(day)

    # we use the publish label because that holds the local timezone. Store label can be deduced from that
    def _snap_back_trading_day_label(self, local: datetime) -> datetime:
        day = self._snap_back_trading_day(local)
        last_trading_day = self._snap_back_trading_week(day)
        return datetime.combine(last_trading_day, time.min, tzinfo=local.tzinfo)

    def _snap_back_trading_week(self, local: date) -> date:
        _, eow = self._weekly_trading_window_days(local)
        if local >= eow:
            return eow
        return local

    def _snap_forward_intraday_interval(self, local: datetime) -> datetime:
        sow, eow = self._weekly_trading_window(local)
        if local < sow:
            return sow
        if local >= eow:
            return sow + ONE_WEEK
        sod, eod = self._daily_trading_window_snapped(local)
        if local < sod:
            return sod
        if local > eod:
            return sod + ONE_DAY
        return local

    def _snap_forward_trading_day(self, local: datetime) -> date:
        _, close = self._daily_trading_window(local)
        day = close.date()
        # close was already snapped to interval here. That is what causes the mismatch
        if local > close:
            day += ONE_DAY
        return self._snap_forward_trading_week(day)

    def _snap_forward_trading_day_label(self, local: datetime) -> datetime:
        day = self._snap_forward_trading_day(local)
        next_trading_day = self._snap_forward_trading_week(day)
        return datetime.combine(next_trading_day, time.min, tzinfo=local.tzinfo)

    def _snap_forward_trading_week(self, local: date) -> date:
        sow, eow = self._weekly_trading_window_days(local)
        if local > eow:
            return sow + ONE_WEEK
        return local

    def _utc_to_local(self, ts: datetime) -> datetime:
        return ts.astimezone(self.timezone)

    def _weekly_trading_window(self, local: datetime) -> tuple[datetime, datetime]:
        open_day, close_day = self._weekly_trading_window_days(local.date())
        open = self._combine_local(open_day, self.market_open)
        close = self._combine_local(close_day, self.market_close)

        # correct weekly window for overnight series (starts the previous day)
        if self._is_overnight():
            open -= ONE_DAY
        return (self.snap_forward_interval(open), self.snap_back_interval(close))

    def _weekly_trading_window_days(self, local: date) -> tuple[date, date]:
        ## determine week start before the local point (% delivers positive)
        start_delta = timedelta(days=(local.weekday() - self.week_start) % 7)
        open_day = local - start_delta
        # determine the week end after the week start
        end_delta = timedelta(days=(self.week_end - self.week_start) % 7)
        close_day = open_day + end_delta
        return open_day, close_day
