# Copyright 2026 Rik Essenius
# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.
# File: src/finance/common/series_calendar.py

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from ..common.model import Series
from ..common.time_utils import parse_duration, parse_weekday, snap_to


@dataclass
class SeriesCalendar:
    interval: timedelta
    timezone: ZoneInfo
    market_open: time
    market_close: time
    week_start: int
    week_end: int
    publication_offset: timedelta | None

    @classmethod
    def from_series(cls, series: Series) -> SeriesCalendar:
        return cls(
            interval=series.interval_delta(),
            timezone=series.timezone,
            market_open=series.market_open,
            market_close=series.market_close,
            week_start=parse_weekday(series.week_start),
            week_end=parse_weekday(series.week_end),
            publication_offset=None
            if series.publication_offset is None
            else parse_duration(series.publication_offset, f"interval for {series.name}"),
        )

    def publication_delta(self, now: datetime) -> timedelta:
        # default is interval, against label time (e.g. 1 day for daily)
        if self.publication_offset is None:
            return self.interval
        # for intraday the offset is against label time, a UTC intraday point
        if self.interval < timedelta(days=1):
            return self.publication_offset

        # DAILY: offset is against *local midnight*
        local_date = self.utc_to_local(now).date()
        local_midnight = datetime.combine(local_date, time.min, tzinfo=self.timezone)
        label_utc = datetime.combine(local_date, time.min, tzinfo=UTC)
        local_publication = local_midnight + self.publication_offset
        publication_utc = self.local_to_utc(local_publication)

        # Offset from label to publication
        return publication_utc - label_utc

    def utc_to_local(self, ts: datetime) -> datetime:
        return ts.astimezone(self.timezone)

    def local_to_utc(self, local: datetime) -> datetime:
        return local.astimezone(UTC)

    def combine_local(self, local_day: date, local_time: time) -> datetime:
        return datetime.combine(local_day, local_time, tzinfo=self.timezone)

    def snap_to_next(self, ts: datetime) -> datetime:
        snapped = snap_to(ts, self.interval)
        if snapped < ts:
            snapped += self.interval
        return snapped

    def snap_to_previous(self, ts: datetime) -> datetime:
        # snap to already snaps to previous
        return snap_to(ts, self.interval)

    def weekly_limits(self, local: datetime) -> tuple[datetime, datetime]:

        # determine week start before the local point (% delivers positive)
        start_delta = timedelta(days=(local.weekday() - self.week_start) % 7)
        anchor_open_day = local.date() - start_delta
        # determine the week end after the week start
        end_delta = timedelta(days=(self.week_end - self.week_start) % 7)

        # weekly_open = week_start + market_open
        open = self.combine_local(anchor_open_day, self.market_open)
        # weekly_close = week_end + market_close
        close = self.combine_local(anchor_open_day + end_delta, self.market_close)

        # correct weekly window for overnight series
        if self.market_open > self.market_close:
            open -= timedelta(days=1)
        return (self.snap_to_next(open), self.snap_to_previous(close))

    def daily_limits(self, local: datetime) -> tuple[datetime, datetime]:
        local_date = local.date()

        open = self.combine_local(local_date, self.market_open)
        close = self.combine_local(local_date, self.market_close)
        if self.market_close == time.max:
            close += timedelta(microseconds=1)
        # correct SOD/EOD in case of overnight series
        if open > close:
            if local < open:
                open -= timedelta(days=1)
            else:
                close += timedelta(days=1)
        return (self.snap_to_next(open), self.snap_to_previous(close))

    def next_label_time_local(self, local: datetime) -> datetime:
        sow, eow = self.weekly_limits(local)
        if local < sow:
            return sow
        if local >= eow:
            return sow + timedelta(weeks=1)
        sod, eod = self.daily_limits(local)
        if local < sod:
            return sod
        if local > eod:
            return sod + timedelta(days=1)
        return local

    # thought: snap_to_previous and the next_publication_time includes offset
    def next_label_time(self, moment_utc: datetime) -> datetime:
        snapped = self.snap_to_next(self.utc_to_local(moment_utc))
        return self.local_to_utc(self.next_label_time_local(snapped))

    def previous_label_time_local(self, local: datetime) -> datetime:
        sow, eow = self.weekly_limits(local)
        if local >= eow:
            return eow
        if local < sow:
            return eow - timedelta(weeks=1)
        sod, eod = self.daily_limits(local)
        if local > eod:
            return eod
        if local < sod:
            return eod - timedelta(days=1)
        return local

    def previous_label_time(self, moment_utc: datetime) -> datetime:
        snapped = self.snap_to_previous(self.utc_to_local(moment_utc))
        return self.local_to_utc(self.previous_label_time_local(snapped))

    def last_label_time_before(self, timestamp: datetime) -> datetime:
        return self.previous_label_time(timestamp - timedelta(microseconds=1))
