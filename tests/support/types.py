# Copyright 2026 Rik Essenius
# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.
# File: tests/support/types.py

from collections.abc import Callable
from contextlib import AbstractContextManager

type Factory[T] = Callable[[], T]
type ConfigurableFactory[T] = Callable[..., T]
type ContextManagerFactory[T] = Callable[..., AbstractContextManager[T]]
