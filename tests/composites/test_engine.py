# Copyright 2026 Rik Essenius
# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.
# File: tests/composites/test_engine.py

import logging
import pytest

from finance.composites.engine import CompositeEngine

# ---------------------------------------------------------
# Helpers
# ---------------------------------------------------------


def make_state(**metrics):
    """
    Convenience helper:
    make_state(
        A_daily = ({"value": 2}, 100),
        B_daily = ({"value": 3}, 200)
    )
    """
    state = {}
    for name, (fields, timestamp) in metrics.items():
        state[name] = {
            "fields": fields,
            "last_timestamp": timestamp,
        }
    return state


# ---------------------------------------------------------
# Identifier rewriting / implicit timeseries
# ---------------------------------------------------------


@pytest.mark.parametrize(
    "expr, expected",
    [
        ("A + B", "A_daily + B_daily"),
        ("A_daily + B", "A_daily + B_daily"),
        ("gold.high - gold.low", "gold_daily.high - gold_daily.low"),
    ],
)
def test_identifier_rewriting(expr, expected):
    composites = {
        "C": {
            "expression": expr,
            "timeseries": "daily",
            "measurement": "test",
            "tags": {},
        }
    }

    state = make_state(
        A_daily=({"value": 2}, 100),
        B_daily=({"value": 3}, 200),
        gold_daily=({"high": 2050, "low": 2000}, 500),
    )

    engine = CompositeEngine(composites, state)
    rewritten = engine._rewrite_expression(expr, "daily")
    assert rewritten == expected


# ---------------------------------------------------------
# Field access
# ---------------------------------------------------------


def test_field_access():
    composites = {
        "RANGE": {
            "expression": "gold.high - gold.low",
            "timeseries": "daily",
            "measurement": "market",
            "tags": {},
        }
    }

    state = make_state(
        gold_daily=({"high": 2050, "low": 2000}, 500),
    )

    engine = CompositeEngine(composites, state)
    result = engine.evaluate_all()

    assert result["RANGE"][0]["value"] == 50
    assert result["RANGE"][1] == 500


# ---------------------------------------------------------
# Composite evaluation (simple, multi-level, independent)
# ---------------------------------------------------------


@pytest.mark.parametrize(
    "composites, state, expected",
    [
        # Simple composite
        (
            {
                "C": {
                    "expression": "A + B",
                    "timeseries": "daily",
                    "measurement": "test",
                    "tags": {},
                }
            },
            make_state(
                A_daily=({"value": 2}, 900),
                B_daily=({"value": 3}, 950),
            ),
            {"C": ({"value": 5}, 950)},
        ),
        # Multi-level composite
        (
            {
                "C": {
                    "expression": "A + B",
                    "timeseries": "daily",
                    "measurement": "test",
                    "tags": {},
                },
                "D": {
                    "expression": "C * 2",
                    "timeseries": "daily",
                    "measurement": "test",
                    "tags": {},
                },
            },
            make_state(
                A_daily=({"value": 1}, 1000),
                B_daily=({"value": 2}, 1100),
                C_daily=({"value": None}, None),
                D_daily=({"value": None}, None),
            ),
            {
                "C": ({"value": 3}, 1100),
                "D": ({"value": 6}, 1100),
            },
        ),
        # Independent composites
        (
            {
                "C": {
                    "expression": "A + B",
                    "timeseries": "daily",
                    "measurement": "test",
                    "tags": {},
                },
                "D": {
                    "expression": "X * 3",
                    "timeseries": "daily",
                    "measurement": "test",
                    "tags": {},
                },
            },
            make_state(
                A_daily=({"value": 1}, 1000),
                B_daily=({"value": 2}, 1100),
                X_daily=({"value": 5}, 2000),
            ),
            {
                "C": ({"value": 3}, 1100),
                "D": ({"value": 15}, 2000),
            },
        ),
    ],
)
def test_composite_evaluation(composites, state, expected):
    engine = CompositeEngine(composites, state)
    result = engine.evaluate_all()

    for key, (fields, ts) in expected.items():
        assert result[key][0] == fields
        assert result[key][1] == ts


# ---------------------------------------------------------
# Error paths (explicit tests)
# ---------------------------------------------------------


def test_missing_dependency(caplog):
    composites = {
        "C": {
            "expression": "A + B",
            "timeseries": "daily",
            "measurement": "test",
            "tags": {},
        }
    }

    state = make_state(
        A_daily=({"value": 1}, 900),
        # B_daily missing
    )

    engine = CompositeEngine(composites, state)

    with caplog.at_level(logging.ERROR):
        result = engine.evaluate_all()

    assert result == {}
    assert "Composite C failed" in caplog.text


def test_syntax_error_in_raw_expression(caplog):
    composites = {
        "C": {
            "expression": "A +",  # invalid raw expression
            "timeseries": "daily",
            "measurement": "test",
            "tags": {},
        }
    }

    state = make_state(
        A_daily=({"value": 1}, 100),
    )

    engine = CompositeEngine(composites, state)

    with caplog.at_level(logging.ERROR):
        result = engine.evaluate_all()

    assert result == {}
    assert "Syntax error" in caplog.text


def test_no_dependencies():
    composites = {
        "X": {
            "expression": "42",
            "timeseries": "daily",
            "measurement": "test",
            "tags": {},
        }
    }

    state = make_state(
        dummy=({"value": 0}, 1234),
    )

    engine = CompositeEngine(composites, state)
    result = engine.evaluate_all()

    assert result["X"][0]["value"] == 42
    assert result["X"][1] == 1234
