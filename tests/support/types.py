# Copyright 2026 Rik Essenius
# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.
# File: tests/support/types.py

from collections.abc import Callable
from contextlib import AbstractContextManager
from datetime import UTC, datetime, timedelta

type Factory[T] = Callable[[], T]
type ConfigurableFactory[T] = Callable[..., T]
type ContextManagerFactory[T] = Callable[..., AbstractContextManager[T]]


class FakeClock:
    def __init__(self):
        self.t = datetime(2025, 6, 15, 15, 6, 40, tzinfo=UTC)

    def __call__(self):
        return self.t

    def advance(self, dt):
        self.t += timedelta(seconds=dt)
