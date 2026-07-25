# Copyright 2026 Rik Essenius
# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.
# File: src/finance/common/result.py

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Generic, TypeVar

T = TypeVar("T")


@dataclass
class Result(Generic[T]):
    ok: bool
    payload: T | None = None
    reason: str | None = None
    error: str | None = None
    warnings: list[str] | None = None
    meta: dict | None = None

    @staticmethod
    def parse_warnings(warnings: list[str]) -> str | None:
        if warnings is None or warnings == []:
            return None
        return warnings

    @staticmethod
    def ok_payload(payload: T, warnings: list[str] | None = None, meta: dict | None = None) -> Result[T]:
        return Result(ok=True, payload=payload, warnings=Result.parse_warnings(warnings), meta=meta)

    @staticmethod
    def fail(
        reason: str, error: str | None = None, warnings: list[str] | None = None, meta: dict | None = None
    ) -> Result[None]:
        return Result(
            ok=False,
            reason=reason,
            error=None if error is None else str(error),
            meta=meta,
            warnings=Result.parse_warnings(warnings),
        )

    def with_measurement(self, measurement: str) -> MeasurementResult[T]:
        return MeasurementResult.from_result(self, measurement)

    def with_meta(self, meta: dict) -> Result:
        return replace(self, meta=meta)


@dataclass
class MeasurementResult(Result[T]):
    # Python quirk: this cannot be non-defaulted as there are defaults in the parent
    series_name: str | None = None

    @staticmethod
    def from_result(result: Result[T], series_name: str) -> MeasurementResult[T]:
        return MeasurementResult(
            ok=result.ok,
            series_name=series_name,
            payload=result.payload,
            reason=result.reason,
            error=result.error,
            warnings=result.warnings,
            meta=result.meta,
        )

    @staticmethod
    def ok_payload(
        series_name: str, payload: T, warnings: list[str] | None = None, meta: dict | None = None
    ) -> MeasurementResult[T]:
        return Result.ok_payload(payload, warnings, meta).with_measurement(series_name)

    @staticmethod
    def fail(
        series_name: str,
        reason: str,
        error: str | None = None,
        warnings: list[str] | None = None,
        meta: dict | None = None,
    ) -> MeasurementResult[None]:
        return Result.fail(reason, error, warnings, meta).with_measurement(series_name)
