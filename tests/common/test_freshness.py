# Copyright 2026 Rik Essenius
# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.
# File: tests/common/test_freshness.py

from finance.common.freshness import is_recent


def test_is_recent_true():
    assert is_recent({"last_try": 100}, now=159, interval=60)


def test_is_recent_false():
    assert not is_recent({"last_try": 100}, now=160, interval=60)


def test_is_recent_false_no_last_try():
    assert not is_recent({}, now=100, interval=60)
