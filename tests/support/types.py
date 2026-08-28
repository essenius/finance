# Copyright 2026 Rik Essenius
# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.
# File: tests/support/types.py

from collections.abc import Callable
from contextlib import AbstractContextManager
from typing import Protocol

from finance.common.types import Result

type Factory[T] = Callable[[], T]
type Creator[T] = Callable[..., T]
type ContextManagerFactory[T] = Callable[..., AbstractContextManager[T]]


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
