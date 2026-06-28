# Copyright 2026 Rik Essenius
# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.
# File: src/finance/common/time_utils.py

import re
from datetime import UTC, date, datetime, time, timedelta

DURATION_UNITS = {
    "s": 1,
    "m": 60,
    "h": 3600,
    "d": 86400,
    "w": 604800,
    "y": 31557600,  # 365.25 days
}


def parse_duration(text: str, context: str | None = None) -> timedelta:
    """
    Convert interval strings like '10m', '1h', '1d', '30s' into seconds.
    Raises ValueError on invalid formats.
    """
    match = re.fullmatch(r"(\d+)([smhdwy])", text)
    if not match:
        context_string = f" in {context}" if context else ""
        raise ValueError(f"Invalid duration '{text}'{context_string}")
    value, unit = match.groups()
    return timedelta(seconds=int(value) * DURATION_UNITS[unit])


def normalize_db_time(value):
    if isinstance(value, datetime):
        return value.astimezone(UTC)
    if isinstance(value, date):
        return datetime.combine(value, time.min, tzinfo=UTC)
    raise TypeError(f"Unexpected time type: {type(value)}")


'''
TODO delete if no longer needed
def to_utc_midnight(local_dt: datetime) -> datetime:
    """
    Given a timezone-aware datetime representing a *local date label*,
    return the UTC midnight that lies inside the validity interval of that date.
    """
    tz = local_dt.tzinfo

    # Validity interval in local time
    start_local = datetime(local_dt.year, local_dt.month, local_dt.day, 0, 0, tzinfo=tz)
    end_local = start_local + timedelta(days=1)

    # Convert interval to UTC
    start_utc = start_local.astimezone(UTC)
    end_utc = end_local.astimezone(UTC)

    # Candidate UTC midnight: same *local* date, but in UTC
    candidate = datetime(local_dt.year, local_dt.month, local_dt.day, 0, 0, tzinfo=UTC)

    # If candidate is inside the interval, use it
    if start_utc <= candidate < end_utc:
        return candidate

    # Otherwise the next UTC midnight must be inside the interval:
    # start_utc <= next_midnight < end_utc. Invalid dates can't happen.
    next_midnight = candidate + timedelta(days=1)
    return next_midnight
'''
