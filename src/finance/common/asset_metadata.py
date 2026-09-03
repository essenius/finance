# Copyright 2026 Rik Essenius
# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.
# File: src/finance/common/asset_metadata.py

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, time
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from ..common.json_utils import JsonObject, JsonReader
from ..common.time_utils import parse_date, parse_time, parse_weekday
from ..common.types import ParseError


@dataclass
class AssetMetadata:
    short_name: str | None = None
    long_name: str | None = None
    instrument: str | None = None
    exchange: str | None = None
    region: str | None = None
    currency: str | None = None
    unit: str | None = None

    timezone: ZoneInfo | None = None
    first_available_date: date | None = None
    market_open: time | None = None
    market_close: time | None = None
    week_start: str | None = None
    week_end: str | None = None

    @classmethod
    def from_config(cls, config: JsonObject) -> AssetMetadata:
        reader = JsonReader(config)
        raw_timezone = reader.get(str, "timezone")
        timezone = None
        if raw_timezone is not None:
            try:
                timezone = ZoneInfo(raw_timezone)
            except ZoneInfoNotFoundError:
                raise ParseError(f"Cannot understand timezone '{raw_timezone}'.") from None

        week_start = reader.get(str, "week_start")
        # check and raise error if filled and wrong, but keep string representation
        parse_weekday(week_start)

        week_end = reader.get(str, "week_end")
        parse_weekday(week_end)

        return cls(
            long_name=reader.get(str, "long_name"),
            short_name=reader.get(str, "short_name"),
            instrument=reader.get(str, "instrument"),
            region=reader.get(str, "region"),
            exchange=reader.get(str, "exchange"),
            currency=reader.get(str, "currency"),
            unit=reader.get(str, "unit"),
            timezone=timezone,
            first_available_date=parse_date(reader.get(str, "first_available_date")),
            week_start=week_start,
            week_end=week_end,
            market_open=parse_time(reader.get(str, "market_open")),
            market_close=parse_time(reader.get(str, "market_close")),
        )

    def __repr__(self) -> str:
        return f"AssetMetadata(short={self.short_name}, currency={self.currency}, timezone={None if self.timezone is None else self.timezone.key})"
