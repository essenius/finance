# Copyright 2026 Rik Essenius
# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.
# File: src/finance/common/candle_identity.py

from dataclasses import dataclass
from datetime import UTC, datetime, time
from functools import total_ordering


@total_ordering
@dataclass
class CandleIdentity:
    is_daily: bool
    value: datetime

    def __init__(self, value: datetime, is_daily: bool):
        self.value = value
        self.is_daily = is_daily

    def __eq__(self, other):
        if not isinstance(other, CandleIdentity):
            return NotImplemented
        return (self.is_daily, self.value) == (other.is_daily, other.value)

    def __lt__(self, other):
        if not isinstance(other, CandleIdentity):
            return NotImplemented
        # Compare by kind first, then by value
        return (self.is_daily, self.value) < (other.is_daily, other.value)

    # with these two, the class automatically supports ==, !=, <, <=, >, >=

    def publish_label(self) -> datetime:
        return self.value

    def store_label(self) -> datetime:
        if self.is_daily:
            return datetime.combine(self.value.date(), time.min, UTC)
        else:
            return self.value.astimezone(UTC)

