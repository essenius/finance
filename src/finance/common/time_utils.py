# Copyright 2026 Rik Essenius
# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.
# File: src/finance/common/time_utils.py

import calendar
import re
from datetime import UTC, date, datetime, time, timedelta, tzinfo
from zoneinfo import ZoneInfo

DURATION_UNITS = {
    "s": 1,
    "m": 60,
    "h": 3600,
    "d": 86400,
    "w": 604800,
    "y": 31557600,  # 365.25 days
}

WEEKDAY_ABBR_MAP = {abbr.lower(): i for i, abbr in enumerate(calendar.day_abbr)}


def parse_duration(text: str, context: str | None = None) -> timedelta | None:
    """
    Convert interval strings like '10m', '1h', '1d', '30s' into seconds.
    Raises ValueError on invalid formats.
    """
    if text is None:
        return None
    if text == "0":
        return timedelta(0)
    match = re.fullmatch(r"(\d+)([smhdwy])", text)
    if not match:
        context_string = f" in {context}" if context else ""
        raise ValueError(f"Invalid duration '{text}'{context_string}")
    value, unit = match.groups()
    return timedelta(seconds=int(value) * DURATION_UNITS[unit])


def check_duration_in(content: dict, name: str, default: str | None = None) -> str:
    """check if the dict content contains a valid duration in the entry with key 'name'.
    If there is no such key, use the default. Raises an error if the duration is not valid."""
    raw_duration = content.get(name, default)
    # validate that the duration is correct
    if raw_duration is not None:
        parse_duration(raw_duration, name)
    return raw_duration


def normalize_db_time(value):
    if isinstance(value, datetime):
        if value.tzinfo is None:
            # Naive → treat as UTC
            return value.replace(tzinfo=UTC, microsecond=0)
        return value.astimezone(UTC).replace(microsecond=0)
    if isinstance(value, date):
        return datetime.combine(value, time.min, tzinfo=UTC)
    raise TypeError(f"Unexpected time type: {type(value)}")


def now_second_precision():
    return datetime.now(tz=UTC).replace(microsecond=0)


def parse_weekday(name: str) -> int | None:
    if name is None:
        return None
    key = name.lower()
    if key not in WEEKDAY_ABBR_MAP:
        raise ValueError(f"Cannot understand day '{key}'.")
    return WEEKDAY_ABBR_MAP[key]


def snap_to(time_point: datetime, range: timedelta) -> datetime:
    delta = range.total_seconds()
    snapped = (time_point.astimezone(UTC).timestamp() // delta) * delta
    return datetime.fromtimestamp(snapped, tz=UTC)


def parse_time(value) -> time | None:
    if value is None:
        return None
    if isinstance(value, int):
        # YAML sexagesimal integer (expects only hh:mm)
        hours = value // 60
        minutes = value % 60
        if hours > 23:
            raise ValueError(
                f"Cannot understand sexagesimal value '{value}' ({hours}:{minutes}). Use hh:mm only or use quotes."
            )
        return time(hour=hours, minute=minutes)

    # used "hh:mm"
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
        raise ValueError(f"Cannot understand time '{value}'.") from None


def write_time(t: time) -> str:
    return time.isoformat(t)


def parse_timezone(s: str) -> ZoneInfo:
    try:
        return ZoneInfo(s)
    except Exception:
        raise ValueError(f"Cannot understand timezone '{s}'.") from None


def write_timezone(tz: tzinfo) -> str:
    # Special-case Python's UTC
    if tz is UTC:
        return "UTC"

    # ZoneInfo: use canonical key
    if hasattr(tz, "key"):
        return tz.key

    raise ValueError("Cannot write timezone without key field")


def parse_datetime(s: str) -> datetime:
    try:
        return datetime.fromisoformat(s) if s is not None else None
    except Exception:
        raise ValueError(f"Cannot understand datetime '{s}'.") from None


def write_datetime(t: time) -> str:
    return datetime.isoformat(t)
