# Copyright 2026 Rik Essenius
# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.
# File: finance/fetch/parser.py


import re

DURATION_UNITS = {
    "s": 1,
    "m": 60,
    "h": 3600,
    "d": 86400,
    "w": 604800,
    "y": 31536000,  # not entirely true (no leap years) but close enough
}


def parse_duration(text: str) -> int:
    match = re.fullmatch(r"(\d+)([smhdwy])", text)
    if not match:
        raise ValueError(f"Invalid duration '{text}'")
    value, unit = match.groups()
    return int(value) * DURATION_UNITS[unit]
