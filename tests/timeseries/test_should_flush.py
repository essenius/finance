# Copyright 2026 Rik Essenius
# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.
# File: tests/timeseries/test_should_flush.py

from finance.common.model import BatchWriteResult


def test_should_flush_empty_pending(backend_v2):
    b = backend_v2
    b._pending = []
    b._pending_bucket = None
    b._last_flush_time = 0
    b.now.advance(100)
    assert not backend_v2._should_flush("any")


def test_should_flush_bucket_switch(backend_v2):
    b = backend_v2
    b._pending = [1]
    b._pending_bucket = "old"
    b._last_flush_time = 0
    b.now.advance(100)
    assert b._should_flush("new")


def test_should_flush_size_threshold(backend_v2):
    b = backend_v2
    b._pending = [1, 2, 3]  # size == max_batch_size
    b._pending_bucket = "same"
    b._last_flush_time = 0
    b.now.advance(1)
    assert b._should_flush("same")


def test_should_flush_age_threshold(backend_v2):
    b = backend_v2
    b._pending = [1]
    b._pending_bucket = "same"
    b._last_flush_time = 0

    # age = 15 > max_batch_age_seconds (10)
    b.now.advance(15)
    assert b._should_flush("same")


def test_should_not_flush_when_no_condition_met(backend_v2):
    b = backend_v2
    b._pending = [1]
    b._pending_bucket = "same"
    b._last_flush_time = 100
    b.now.advance(101)
    # age = 2 < threshold, size < threshold, bucket same
    assert not b._should_flush("same")


def test_flush_pending_full_success(backend_v2, make_entry, monkeypatch):
    b = backend_v2
    e1 = make_entry()
    e2 = make_entry()
    b._pending = [e1, e2]
    b._pending_bucket = "bucket"

    def fake_batch(entries):
        return BatchWriteResult(ok=True, succeeded=[0, 1], failed=[])

    monkeypatch.setattr(b, "batch_write_v2", fake_batch)

    result = b._flush_pending()

    assert result.ok
    assert b._pending == []
    assert b._pending_bucket is None


def test_flush_pending_partial_failure(backend_v2, make_entry, monkeypatch):
    b = backend_v2
    e1 = make_entry()
    e2 = make_entry()
    b._pending = [e1, e2]
    b._pending_bucket = "bucket"

    def fake_batch(entries):
        return BatchWriteResult(
            ok=False,
            succeeded=[0],
            failed=[1],
            warnings=["line 1 failed"],
        )

    monkeypatch.setattr(b, "batch_write_v2", fake_batch)

    result = b._flush_pending()

    assert not result.ok
    assert b._pending == [e2]  # only failed entry remains
    assert b._pending_bucket == "bucket"
    assert result.warnings == ["line 1 failed"]


def test_flush_pending_catastrophic_failure(backend_v2, make_entry, monkeypatch):
    b = backend_v2
    e1 = make_entry()
    e2 = make_entry()
    b._pending = [e1, e2]
    b._pending_bucket = "bucket"

    def fake_batch(entries):
        raise RuntimeError("boom")

    monkeypatch.setattr(b, "batch_write_v2", fake_batch)

    result = b._flush_pending()

    assert not result.ok
    assert result.failed == [0, 1]
    assert result.meta["exception"] == "boom"
    assert b._pending == [e1, e2]  # all preserved
