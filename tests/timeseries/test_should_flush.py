# Copyright 2026 Rik Essenius
# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.
# File: tests/timeseries/test_should_flush.py


def test_should_not_flush_empty_pending(make_backend):
    b = make_backend()
    b._pending = []
    assert not b._should_flush()


def test_should_not_flush_size_threshold(make_backend):
    b = make_backend(max_batch_size=2, max_batch_age_seconds=2)
    b._pending = [1]
    assert not b._should_flush()


def test_should_flush_size_threshold(make_backend):
    b = make_backend(max_batch_size=2, max_batch_age_seconds=2)
    b._pending = [1, 2]
    assert b._should_flush()


def test_should_flush_age_threshold(make_backend):
    b = make_backend(max_batch_size=4, max_batch_age_seconds=10)
    b._pending = [1]
    assert not b._should_flush(), "init _last_flush"
    b.now.advance(9)
    b._pending.append(2)
    assert not b._should_flush(), "no timeout yet"
    b.now.advance(1)
    b._pending.append(3)
    assert b._should_flush(), "timeout"
