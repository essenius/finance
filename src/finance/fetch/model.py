# Copyright 2026 Rik Essenius
# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.
# File: src/finance/fetch/model.py

from dataclasses import dataclass


@dataclass(frozen=True)
class FrequencyConfig:
    name: str
    interval: str
    fields: list[str]


@dataclass(frozen=True)
class Asset:
    name: str
    provider: str
    provider_symbol: str
    frequencies: list[FrequencyConfig]


@dataclass
class Candle:
    timestamp: int
    open: float
    high: float
    low: float
    close: float
    volume: float

    def is_valid(self) -> bool:
        return None not in (
            self.timestamp,
            self.open,
            self.high,
            self.low,
            self.close,
            self.volume,
        )

    def to_dict(self):
        return {
            "timestamp": self.timestamp,
            "fields": {
                "open": self.open,
                "high": self.high,
                "low": self.low,
                "close": self.close,
                "volume": self.volume,
            },
        }
