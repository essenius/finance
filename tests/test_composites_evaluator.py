# Copyright 2026 Rik Essenius
# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.
# File: tests/test_composites_evaluator.py

import pytest
from finance.composites.evaluator import evaluate_expression, extract_values_and_timestamps, evaluate_composites

# -------------------------
# Evaluate Expression
# -------------------------

def test_evaluate_expression_simple():
    assert evaluate_expression("A + B", {"A": 2, "B": 3}) == 5

def test_evaluate_expression_raises():
    with pytest.raises(ValueError):
        evaluate_expression("A + unknown", {"A": 1})

# ------------------------------
# Extract Values and Timestamps
# ------------------------------

def test_extract_values_and_timestamps():
    state = {
        "A": {"last_value": 1, "last_timestamp": 10},
        "B": {"last_value": 2, "last_timestamp": 20},
    }
    values, ts = extract_values_and_timestamps(state, ["A", "B"])
    assert values == {"A": 1, "B": 2}
    assert ts == [10, 20]


def test_extract_values_and_timestamps_missing():
    state = {
        "A": {"last_value": 1, "last_timestamp": 10},
        # B missing
    }
    with pytest.raises(KeyError):
        extract_values_and_timestamps(state, ["A", "B"])
        
# -------------------------
# Evaluate Composites
# -------------------------

# We patch time.time so tests are deterministic
import time

class FixedTime:
    def __init__(self, value):
        self.value = value

    def __call__(self):
        return self.value


def test_simple_composite(monkeypatch):
    # Freeze time
    monkeypatch.setattr(time, "time", FixedTime(1000))

    composites = {"C": "A + B"}
    state = {
        "A": {"last_value": 2, "last_timestamp": 900},
        "B": {"last_value": 3, "last_timestamp": 950},
    }

    result = evaluate_composites(composites, state)

    assert result["C"][0] == 5
    assert result["C"][1] == 950  # newest timestamp


def test_multi_level_composites(monkeypatch):
    monkeypatch.setattr(time, "time", FixedTime(2000))

    composites = {
        "C": "A + B",
        "D": "C * 2",
    }

    state = {
        "A": {"last_value": 1, "last_timestamp": 1000},
        "B": {"last_value": 2, "last_timestamp": 1100},
        "C": {"last_value": None, "last_timestamp": None},
        "D": {"last_value": None, "last_timestamp": None},
    }

    result = evaluate_composites(composites, state)

    assert result["C"][0] == 3
    assert result["C"][1] == 1100
    assert result["D"][0] == 6
    assert result["D"][1] == 1100


def test_missing_dependency(monkeypatch):
    monkeypatch.setattr(time, "time", FixedTime(1000))

    composites = {"C": "A + B"}
    state = {
        "A": {"last_value": 1, "last_timestamp": 900},
        # B missing
    }

    result = evaluate_composites(composites, state)

    # Missing dependency → composite skipped
    assert result == {}


def test_no_dependencies(monkeypatch):
    monkeypatch.setattr(time, "time", FixedTime(1234))

    composites = {"X": "42"}
    state = {"X": {"last_value": None, "last_timestamp": None}}

    result = evaluate_composites(composites, state)

    assert result["X"][0] == 42
    assert result["X"][1] == 1234  # now


def test_multiple_independent_composites(monkeypatch):
    monkeypatch.setattr(time, "time", FixedTime(3000))

    composites = {
        "C": "A + B",
        "D": "X * 3",
    }

    state = {
        "A": {"last_value": 1, "last_timestamp": 1000},
        "B": {"last_value": 2, "last_timestamp": 1100},
        "X": {"last_value": 5, "last_timestamp": 2000},
    }

    result = evaluate_composites(composites, state)

    assert result["C"][0] == 3
    assert result["C"][1] == 1100

    assert result["D"][0] == 15
    assert result["D"][1] == 2000


def test_composite_always_recomputes(monkeypatch):
    monkeypatch.setattr(time, "time", lambda: 5000)

    composites = {"C": "A + B"}
    state = {
        "A": {"last_value": 10, "last_timestamp": 4000},
        "B": {"last_value": 20, "last_timestamp": 4500},
        "C": {"last_value": 999, "last_timestamp": 4800, "last_try": 4990},
    }

    result = evaluate_composites(composites, state)

    # Should recompute regardless of freshness
    assert "C" in result
    value, ts = result["C"]
    assert value == 30
    assert ts == 4500  # newest dependency timestamp
