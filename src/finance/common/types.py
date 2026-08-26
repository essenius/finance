# Copyright 2026 Rik Essenius
# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.
# File: src/finance/common/types.py

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Literal


class AppError(Exception):
    pass


class ParseError(AppError):
    pass


@dataclass
class Success[T]:
    payload: T
    warnings: list[str] = field(default_factory=list)
    meta: Mapping[str, object] | None = None
    ok: Literal[True] = True

    def to_log_dict(self) -> dict[str, object]:
        # log doesn't include the payload as that can be quite large
        return {
            "warnings": self.warnings,
            "meta": self.meta,
        }


@dataclass
class Failure:
    reason: str
    error: str | Exception | None = None
    warnings: list[str] = field(default_factory=list)
    meta: Mapping[str, object] | None = None
    ok: Literal[False] = False

    def to_log_dict(self) -> dict[str, object]:
        return {
            "reason": self.reason,
            "error": self.error,
            "warnings": self.warnings,
            "meta": self.meta,
        }


type Result[T] = Success[T] | Failure
