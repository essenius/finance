# Copyright 2026 Rik Essenius
# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.
# File: tests/support/types.py

from collections.abc import Callable
from contextlib import AbstractContextManager
from dataclasses import dataclass
from typing import Protocol
from unittest.mock import Mock

from finance.common.model import Series, SeriesPoint
from finance.common.types import Result
from finance.state.state import State

type Factory[T] = Callable[[], T]
type Creator[T] = Callable[..., T]
type ContextManagerFactory[T] = Callable[..., AbstractContextManager[T]]
type StateContext = tuple[State, Mock, Mock]


class AssertError(Protocol):
    def __call__(
        self,
        result: Result,
        reason: str,
        error: str | None = None,
    ) -> None: ...


class AssertWarning[T](Protocol):
    def __call__(
        self,
        result: Result[T],
        warning: str,
    ) -> None: ...


@dataclass
class WalContext:
    point: SeriesPoint
    series: Series
