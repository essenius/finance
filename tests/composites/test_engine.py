# Copyright 2026 Rik Essenius
# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.
# File: tests/composites/test_engine.py

import pytest

from finance.composites.engine import CompositeEngine
from finance.state.manager import State

# ---------------------------------------------------------
# Helpers
# ---------------------------------------------------------


def make_state(state: State, **metrics):
    """
    Convenience helper:
    make_state(
        A_daily = ({"value": 2}, 100),
        B_daily = ({"value": 3}, 200)
    )
    """
    for name, (fields, timestamp) in metrics.items():
        state.data[name] = {
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
def test_identifier_rewriting(expr, expected, unwrap, state_obj):
    composites = {
        "C": {
            "expression": expr,
            "timeseries": "daily",
            "measurement": "test",
            "tags": {},
        }
    }

    state = make_state(state_obj,
        A_daily=({"value": 2}, 100),
        B_daily=({"value": 3}, 200),
        gold_daily=({"high": 2050, "low": 2000}, 500),
    )


    engine = unwrap(CompositeEngine.build(composites, state))
    rewritten = engine._rewrite_expression(expr, "daily")
    assert rewritten == expected


# ---------------------------------------------------------
# Field access
# ---------------------------------------------------------


def test_field_access(unwrap, state_obj):
    composites = {
        "RANGE": {
            "expression": "gold.high - gold.low",
            "timeseries": "daily",
            "measurement": "market",
            "tags": {},
        }
    }

    state = make_state(state_obj, gold_daily=({"high": 2050, "low": 2000}, 500))

    engine = unwrap(CompositeEngine.build(composites, state))
    result_list = list(engine.evaluate_incrementally())
    assert not result_list[0].error
    result = unwrap(result_list[0])
    assert result[0].fields["value"] == 50
    assert result[0].timestamp == 500


# ---------------------------------------------------------
# Composite evaluation (simple, multi-level, independent)
# ---------------------------------------------------------


@pytest.mark.parametrize(
    "composites, initial_metrics, expected",
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
            {
                "A_daily": ({"value": 2}, 900),
                "B_daily": ({"value": 3}, 950),
            },
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
            {
                "A_daily": ({"value": 1}, 1000),
                "B_daily": ({"value": 2}, 1100),
                "C_daily": ({"value": None}, None),
                "D_daily": ({"value": None}, None),
            },
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
            {
                "A_daily": ({"value": 1}, 1000),
                "B_daily": ({"value": 2}, 1100),
                "X_daily": ({"value": 5}, 2000),
            },
            {
                "C": ({"value": 3}, 1100),
                "D": ({"value": 15}, 2000),
            },
        ),
    ],
)
def test_composite_evaluation(unwrap, state_obj, composites, initial_metrics, expected):

    state = make_state(state_obj, **initial_metrics)
    engine = unwrap(CompositeEngine.build(composites, state))
    list(engine.evaluate_incrementally())
    for key, (fields, ts) in expected.items():
        metric = f"{key}_daily"
        entry = state.get(metric)
        assert entry["fields"] == fields
        assert entry["last_timestamp"] == ts


# ---------------------------------------------------------
# Error paths (explicit tests)
# ---------------------------------------------------------


def test_missing_dependency(unwrap, assert_error, state_obj):
    composites = {
        "C": {
            "expression": "A + B",
            "timeseries": "daily",
            "measurement": "test",
            "tags": {},
        }
    }

    state = make_state(state_obj,
        A_daily=({"value": 1}, 900),
        # B_daily missing
    )

    engine = unwrap(CompositeEngine.build(composites, state))

    results = list(engine.evaluate_incrementally())

        # Expect exactly one failure
    fail = [r for r in results if not r.ok]
    assert len(fail) == 1

    fr = fail[0]
    assert fr.measurement == "C"
    assert_error(fr, "failed", "name 'B' is not defined")

    # No composite should be written to state
    assert state.data.get("C_daily") is None


def test_syntax_error_in_raw_expression(state_obj):
    composites = {
        "C": {
            "expression": "A +",  # invalid raw expression
            "timeseries": "daily",
            "measurement": "test",
            "tags": {},
        }
    }

    state = make_state(state_obj, A_daily=({"value": 1}, 100))

    engine = CompositeEngine.build(composites, state)
    assert not engine.ok
    assert "Syntax error in composite expression 'A +'" in engine.reason
    assert "invalid syntax (<unknown>, line 1)" in engine.error

    # No composite should be written to state
    assert state.data.get("C_daily") is None


def test_no_dependencies(unwrap, state_obj):
    composites = {
        "X": {
            "expression": "42",
            "timeseries": "daily",
            "measurement": "test",
            "tags": {},
        }
    }

    state = make_state(state_obj, dummy=({"value": 0}, 1234))

    engine = unwrap(CompositeEngine.build(composites, state))
    list(engine.evaluate_incrementally())

    entry = state.get("X_daily")
    assert entry["fields"]["value"] == 42
    assert entry["last_timestamp"] == 1234

def test_cycle_error_in_build(state_obj, assert_error):
    composites = {
        "A": {
            "expression": "A",   # self-reference
            "timeseries": "daily",
            "measurement": "test",
            "tags": {},
        }
    }

    result = CompositeEngine.build(composites, state_obj)
    assert_error(result, "Error in topo_sort", "Cycle detected at A")
