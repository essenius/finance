# Copyright 2026 Rik Essenius
# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.
# File: src/finance/common/time_utils.py

import calendar
import re
from datetime import date, datetime, time, timedelta
from typing import overload
from zoneinfo import ZoneInfo

from ..common.types import ParseError

# UTC based on ZoneInfo instead of tzinfo. Then we have a consistent model
UTC = ZoneInfo("UTC")

DURATION_UNITS = {
    "s": 1,
    "m": 60,
    "h": 3600,
    "d": 86400,
    "w": 604800,
    "y": 31557600,  # 365.25 days
}

WEEKDAY_ABBR_MAP = {abbr.lower(): i for i, abbr in enumerate(calendar.day_abbr)}


def normalize_db_time(value) -> datetime:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            # Naive → treat as UTC
            return value.replace(tzinfo=UTC, microsecond=0)
        return value.astimezone(UTC).replace(microsecond=0)
    if isinstance(value, date):
        return datetime.combine(value, time.min, tzinfo=UTC)
    raise TypeError(f"Unexpected time type: {type(value)}")


def now_second_precision() -> datetime:
    return datetime.now(tz=UTC).replace(microsecond=0)


@overload
def parse_duration(text: None, context: str | None = None) -> None: ...
@overload
def parse_duration(text: str, context: str | None = None) -> timedelta: ...


def parse_duration(text: str | None, context: str | None = None) -> timedelta | None:
    """
    Convert interval strings like '10m', '1h', '1d', '30s' into seconds.
    Raises ParseError on invalid formats.
    """
    if text is None:
        return None
    if text == "0":
        return timedelta(0)
    match = re.fullmatch(r"(\d+)([smhdwy])", text)
    if not match:
        context_string = f" in {context}" if context else ""
        raise ParseError(f"Invalid duration '{text}'{context_string}")
    value, unit = match.groups()
    return timedelta(seconds=int(value) * DURATION_UNITS[unit])


def parse_date(s: str | None) -> date | None:
    try:
        return date.fromisoformat(s) if s is not None else None
    except Exception:
        raise ParseError(f"Cannot understand date '{s}'.") from None


def parse_datetime(s: str | None) -> datetime | None:
    try:
        return datetime.fromisoformat(s) if s is not None else None
    except Exception:
        raise ParseError(f"Cannot understand datetime '{s}'.") from None


def parse_time(value: str | None) -> time | None:
    if value is None:
        return None

    value = str(value).strip().lower()
    if value == "min":
        return time.min
    if value == "max":
        return time.max

    # Normalize single-digit hour → pad to HH:MM...
    parts = value.split(":")
    if len(parts[0]) == 1:
        parts[0] = "0" + parts[0]
        value = ":".join(parts)
    try:
        return time.fromisoformat(value)
    except Exception:
        raise ParseError(f"Cannot understand time '{value}'.") from None


def parse_weekday(name: str | None) -> int | None:
    if name is None:
        return None
    key = name.lower()
    if key not in WEEKDAY_ABBR_MAP:
        raise ParseError(f"Cannot understand day '{key}'.")
    return WEEKDAY_ABBR_MAP[key]


def snap_to(time_point: datetime, range: timedelta) -> datetime:
    delta = range.total_seconds()
    snapped = (time_point.astimezone(UTC).timestamp() // delta) * delta
    return datetime.fromtimestamp(snapped, tz=UTC)


def validate_duration(text: str | None, context: str | None = None) -> str | None:
    parse_duration(text, context)
    return text


def write_date(d: date) -> str:
    return date.isoformat(d)


def write_datetime(dt: datetime) -> str:
    return datetime.isoformat(dt)


def write_time(t: time | None) -> str | None:
    if t is None:
        return None
    return time.isoformat(t)


def write_timezone(tz: ZoneInfo | None) -> str | None:

    if tz is None:
        return None

    return tz.key


def view_utc(d: datetime) -> str:
    if d.hour == 0 and d.minute == 0 and d.second == 0:
        return d.strftime("%Y-%m-%d")
    return d.strftime("%Y-%m-%d %H:%M")
