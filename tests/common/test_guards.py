# Copyright 2026 Rik Essenius
# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.
# File: tests/common/test_guards.py

from datetime import timedelta

import pytest

from finance.common.guards import require, require_duration, require_key, validate_required_duration


def test_require():
    assert require("x", "X") == "x"
    with pytest.raises(ValueError) as ve:
        require(None, "N")
    assert "Missing required value in N" in str(ve)


def test_require_key():
    config = {"x": 1, "y": "z"}
    assert require_key(config, "x", "X") == 1
    assert require_key(config, "y", "Y") == "z"
    with pytest.raises(ValueError) as ve:
        require_key(config, "z", "Z")
    assert "Missing required field 'z' in Z" in str(ve)
    with pytest.raises(ValueError) as ve:
        require_key({}, "z", "Z")
    assert "Missing required field 'z' in Z" in str(ve)


def test_require_duration():
    assert require_duration("1d", "interval") == timedelta(days=1)
    with pytest.raises(ValueError) as ve:
        require_duration(None, "interval")
    assert "Missing required value in interval" in str(ve)


def test_validate_required_duration():
    assert validate_required_duration("1d", "interval") == "1d"
    with pytest.raises(ValueError) as ve:
        validate_required_duration(None, "interval")
    assert "Missing required value in interval" in str(ve)
