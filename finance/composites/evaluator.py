# Copyright 2026 Rik Essenius
# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.
# File: finance/composites/evaluator.py

import time
from .deps import build_composite_graph, topo_sort

def extract_values_and_timestamps(state, deps):
    values = {}
    timestamps = []

    for dep in deps:
        dep_state = state.get(dep)
        if not dep_state or dep_state["last_value"] is None:
            raise KeyError(f"Missing dependency {dep}")

        values[dep] = dep_state["last_value"]
        timestamps.append(dep_state["last_timestamp"])

    return values, timestamps

def evaluate_expression(expr, values):
    """Evaluate a composite expression using only provided values."""
    try:
        return eval(expr, {}, values)
    except Exception as e:
        raise ValueError(f"Error evaluating expression '{expr}'") from e

def evaluate_composites(composites, state):
    computed = {}
    now = int(time.time())

    graph = build_composite_graph(composites, state)

    # Evaluate in topological order
    for measurement in topo_sort(graph):
        expr = composites[measurement]
        entry = state.get(measurement, {})

        deps = graph[measurement]

        try:
            values, timestamps = extract_values_and_timestamps(state, deps)
            value = evaluate_expression(expr, values)
            ts = max(timestamps) if timestamps else now
            computed[measurement] = (value, ts)

            state[measurement] = {
                "last_value": value,
                "last_timestamp": ts,
                "last_try": now,
            }

        except Exception:
            # Log or skip — your choice
            continue

    return computed
