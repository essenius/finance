# Copyright 2026 Rik Essenius
# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.
# File: tests/timeseries/test_should_flush.py


from datetime import datetime

from finance.common.model import SeriesPoint
from tests.support.fakes import FakeBackend
from tests.support.types import Creator

SP1 = SeriesPoint(1, datetime(1, 1, 1), 1.0)
SP2 = SeriesPoint(2, datetime(1, 1, 1), 2.0)
SP3 = SeriesPoint(3, datetime(1, 1, 1), 3.0)


def test_should_not_flush_empty_pending(make_backend: Creator[FakeBackend]):
    backend = make_backend().only()
    backend._pending = []
    assert not backend._should_flush()


def test_should_not_flush_size_threshold(make_backend: Creator[FakeBackend]):
    backend = make_backend(max_batch_size=2, max_batch_age_seconds=2).only()
    backend._pending = [SP1]
    assert not backend._should_flush()


def test_should_flush_size_threshold(make_backend: Creator[FakeBackend]):
    backend = make_backend(max_batch_size=2, max_batch_age_seconds=2).only()
    backend._pending = [SP1, SP2]
    assert backend._should_flush()


def test_should_flush_age_threshold(make_backend: Creator[FakeBackend]):
    backend, clock = make_backend(max_batch_size=4, max_batch_age_seconds=10).with_clock()
    backend._pending = [SP1]
    assert not backend._should_flush(), "init _last_flush"
    clock.advance(9)
    backend._pending.append(SP2)
    assert not backend._should_flush(), "no timeout yet"
    clock.advance(1)
    backend._pending.append(SP3)
    assert backend._should_flush(), "timeout"
