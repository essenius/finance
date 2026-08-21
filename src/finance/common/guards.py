# Copyright 2026 Rik Essenius
# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.
# File: src/finance/common/guards.py

from datetime import timedelta

from finance.common.time_utils import parse_duration


def require[T](value: T | None, context: str) -> T:
    if value is None:
        raise ValueError(f"Missing required value in {context}")
    return value


def require_key(cfg: dict, key: str, context: str) -> object:
    """
    Return cfg[key] if present, otherwise raise a ValueError.
    This has to be caught in the function it is used in.
    """
    if key not in cfg:
        raise ValueError(f"Missing required field '{key}' in {context}")
    return cfg[key]


def require_duration(text: str | None, context: str) -> timedelta:
    return require(parse_duration(text, context), context)


def validate_required_duration(text: str | None, context: str) -> str:
    text = require(text, context)
    require_duration(text, context)
    return text
