# Copyright 2026 Rik Essenius
# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.
# File: src/finance/common/guards.py

from datetime import timedelta

from ..common.time_utils import parse_duration
from ..common.types import ParseError


def require[T](value: T | None, context: str = "") -> T:
    if value is None:
        context = _annotate(context)
        raise ParseError(f"Missing required value{context}")
    return value


def require_duration(text: str | None, context: str = "") -> timedelta:
    return require(parse_duration(text, context), context)


def validate_required_duration(text: str | None, context: str = "") -> str:
    text = require(text, context)
    require_duration(text, context)
    return text


# ----------------
# Private methods
# ----------------


def _annotate(context: str) -> str:
    if context != "":
        return " in " + context
    return ""
