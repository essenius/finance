# Copyright 2026 Rik Essenius
# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.
# File: tests/common/test_introspection.py

from finance.common.introspection import here


def test_here():
    assert here() == "test_here"
