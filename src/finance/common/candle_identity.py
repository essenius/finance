# Copyright 2026 Rik Essenius
# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.
# File: src/finance/common/candle_identity.py

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from functools import total_ordering
from zoneinfo import ZoneInfo

from ..common.time_utils import UTC


@total_ordering
@dataclass
class CandleIdentity:
    is_daily: bool
    value: datetime
    interval: timedelta

    @classmethod
    def from_timestamp(cls, timestamp: int, timezone: ZoneInfo, interval: timedelta) -> CandleIdentity:
        is_daily = interval >= timedelta(days=1)
        value = datetime.fromtimestamp(timestamp, tz=timezone)
        return cls(value, is_daily, interval)

    def __init__(self, value: datetime, is_daily: bool, interval: timedelta):
        self.value = value
        self.is_daily = is_daily
        self.interval = interval

    def __eq__(self, other: CandleIdentity) -> bool:
        if not isinstance(other, CandleIdentity):
            return NotImplemented
        return (self.is_daily, self.value) == (other.is_daily, other.value)

    def __lt__(self, other: CandleIdentity) -> bool:
        if not isinstance(other, CandleIdentity):
            return NotImplemented
        # Compare by kind first, then by value
        return (self.is_daily, self.value) < (other.is_daily, other.value)

    # with these two, the class automatically supports ==, !=, <, <=, >, >=

    def date(self) -> date:
        return self.value.date()

    def end_timestamp(self) -> int:
        if self.is_daily:
            # allow any time in the label period, to allow for publishers using start-of-day or end-of-day
            # note this is only used to calculate the fetch period based on already determined identities
            return int((self.value + self.interval).timestamp() - 1)
        return int(self.value.timestamp())

    def publish_label(self) -> datetime:
        return self.value

    def start_timestamp(self) -> int:
        return int(self.value.timestamp())

    def store_label(self) -> datetime:
        if self.is_daily:
            return datetime.combine(self.value.date(), time.min, UTC)
        else:
            return self.value.astimezone(UTC)
