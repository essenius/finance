# Copyright 2026 Rik Essenius
# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.
# File: src/finance/fetch/model.py

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Generic, TypeVar


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

    def to_point(self, fields: list[str] | None = None) -> FetchPoint:
        candle_fields = ("open", "high", "low", "close", "volume")
        all_fields = {name: getattr(self, name) for name in candle_fields}

        if fields is None:
            selected = all_fields
        else:
            # compare against keys only
            selected = {name: all_fields[name] for name in fields if name in all_fields}

        return FetchPoint(fields=selected, timestamp=self.timestamp)


@dataclass
class FetchPoint:
    fields: dict
    timestamp: int


T = TypeVar("T")


@dataclass
class Result(Generic[T]):
    ok: bool
    payload: T | None = None
    reason: str | None = None
    error: str | None = None
    warning: str | None = None
    meta: dict | None = None

    @staticmethod
    def parse_warnings(warnings: list[str]) -> str | None:
        if warnings is None or warnings == []:
            return None
        return "\n".join(warnings)

    @staticmethod
    def ok_payload(payload: T, warnings: list[str]|None = None, meta: dict | None = None) -> Result[T]:
        return Result(ok=True, payload=payload, warning=Result.parse_warnings(warnings), meta=meta)

    @staticmethod
    def fail(reason: str, error: str | None = None, warnings: list[str]|None = None, meta: dict | None = None) -> Result[None]:
        return Result(ok=False, reason=reason, error=None if error is None else str(error), meta=meta, warning=Result.parse_warnings(warnings))

    def with_measurement(self, measurement: str) -> MeasurementResult[T]:
        return MeasurementResult.from_result(self, measurement)


@dataclass
class MeasurementResult(Result[T]):
    # Python quirk: this cannot be non-defaulted as there are defaults in the parent
    measurement: str | None = None

    @staticmethod
    def from_result(result: Result[T], measurement: str) -> MeasurementResult[T]:
        return MeasurementResult(
            ok=result.ok,
            measurement=measurement,
            payload=result.payload,
            reason=result.reason,
            error=result.error,
            warning=result.warning,
            meta=result.meta,
        )

    @staticmethod
    def ok_payload(measurement: str, payload: T, warnings: list[str]|None = None, meta: dict|None = None) -> MeasurementResult[T]:
        return Result.ok_payload(payload, warnings, meta).with_measurement(measurement)

    @staticmethod
    def fail(measurement: str, reason: str, error: str | None = None, warnings: list[str]|None = None, meta: dict | None = None) -> MeasurementResult[None]:
        return Result.fail(reason, error, warnings, meta).with_measurement(measurement)

FetchResult = MeasurementResult[list[FetchPoint]]

@dataclass
class TimeseriesWrite:
    measurement: str
    fields: Mapping[str, float | int | str]
    tags: Mapping[str, str]
    timestamp: int
    bucket: str


TimeseriesResult = MeasurementResult[TimeseriesWrite|None]
