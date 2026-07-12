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
        return value.astimezone(UTC)
    if isinstance(value, date):
        return datetime.combine(value, time.min, tzinfo=UTC)
    raise TypeError(f"Unexpected time type: {type(value)}")
