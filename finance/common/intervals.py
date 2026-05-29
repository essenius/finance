# Copyright 2026 Rik Essenius
# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.
# File: finance/common/intervals.py


def parse_interval(s: str) -> int:
    """
    Convert interval strings like '10m', '1h', '1d', '30s' into seconds.
    Raises ValueError on invalid formats.
    """
    if not isinstance(s, str) or len(s) < 2:
        raise ValueError(f"Invalid interval: {s}")

    unit = s[-1]
    value_str = s[:-1]

    try:
        value = int(value_str)
    except ValueError:
        raise ValueError(f"Invalid interval value: {s}") from None

    if unit == "s":
        return value
    if unit == "m":
        return value * 60
    if unit == "h":
        return value * 3600
    if unit == "d":
        return value * 86400

    raise ValueError(f"Invalid interval unit: {s}")
