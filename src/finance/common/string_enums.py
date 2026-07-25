# Copyright 2026 Rik Essenius
# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.
# File: src/finance/common/string_enums.py

from __future__ import annotations

from enum import StrEnum


class StringEnum(StrEnum):
    @classmethod
    def contains(cls, value: str) -> bool:
        return value in cls._value2member_map_

    @classmethod
    def values(cls) -> list[str]:
        return [entry.value for entry in cls]

    @classmethod
    def validate(cls, value: str, context: str = "") -> str:
        if context != "":
            context = f" in {context}"
        try:
            return cls(value).value
        except ValueError:
            raise ValueError(f"Invalid {cls.__name__}{context}: {value!r}. Allowed: {cls.values()}") from None


class Candle(StringEnum):
    OPEN = "open"
    HIGH = "high"
    LOW = "low"
    CLOSE = "close"
    VOLUME = "volume"

    @classmethod
    def ordered(cls) -> list[Candle]:
        return [cls.OPEN, cls.HIGH, cls.LOW, cls.CLOSE, cls.VOLUME]


class Retention(StringEnum):
    # note: defined in setup.sql too
    SHORT_LIVED = "short_lived"
    LONG_LIVED = "long_lived"


class SeriesType(StringEnum):
    # note: defined in setup.sql too
    CANDLE = "candle"
    VALUE = "value"


class SupportedProviders(StringEnum):
    YAHOO = "yahoo"
    ECB = "ecb"
    FRED = "fred"
