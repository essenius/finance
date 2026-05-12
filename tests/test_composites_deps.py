# Copyright 2026 Rik Essenius
# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.
# File: tests/test_composites_deps.py

import pytest

from finance.composites.deps import (
    CycleError,
    build_composite_graph,
    extract_dependencies,
    topo_sort,
)

# -------------------------
#  Topo Sort Valid DAGs
# -------------------------

def test_empty_graph():
    graph = {}
    assert topo_sort(graph) == []

def test_single_node():
    graph = {"a": []}
    assert topo_sort(graph) == ["a"]

def test_two_independent_nodes():
    graph = {"a": [], "b": []}
    result = topo_sort(graph)
    assert set(result) == {"a", "b"}
    assert len(result) == 2


def test_simple_chain():
    graph = {"c": ["b"], "b": ["a"], "a": []}
    assert topo_sort(graph) == ["a", "b", "c"]


def test_diamond_graph():
    graph = {
        "d": ["b", "c"],
        "b": ["a"],
        "c": ["a"],
        "a": []
    }
    result = topo_sort(graph)
    assert result.index("a") < result.index("b")
    assert result.index("a") < result.index("c")
    assert result.index("b") < result.index("d")
    assert result.index("c") < result.index("d")


def test_multiple_roots():
    graph = {"x": [], "y": [], "z": ["x", "y"]}
    result = topo_sort(graph)
    assert result.index("x") < result.index("z")
    assert result.index("y") < result.index("z")


def test_depends_on_non_composite_ignored():
    graph = {"a": ["base1"]}  # base1 not in graph → ignored
    assert topo_sort(graph) == ["a"]


def test_mixed_dependencies():
    graph = {
        "c": ["a", "b", "external"],
        "a": [],
        "b": []
    }
    result = topo_sort(graph)
    assert result.index("a") < result.index("c")
    assert result.index("b") < result.index("c")


def test_wide_graph():
    graph = {
        "z": ["a", "b", "c", "d", "e"],
        "a": [], "b": [], "c": [], "d": [], "e": []
    }
    result = topo_sort(graph)
    for parent in ["a", "b", "c", "d", "e"]:
        assert result.index(parent) < result.index("z")


def test_deep_graph():
    graph = {
        "n5": ["n4"],
        "n4": ["n3"],
        "n3": ["n2"],
        "n2": ["n1"],
        "n1": []
    }
    assert topo_sort(graph) == ["n1", "n2", "n3", "n4", "n5"]


def test_unordered_input_keys():
    graph = {
        "c": ["b"],
        "a": [],
        "b": ["a"]
    }
    assert topo_sort(graph) == ["a", "b", "c"]


# -------------------------
#  Topo Sort Cycles
# -------------------------

def test_cycle_two_nodes():
    graph = {"a": ["b"], "b": ["a"]}
    with pytest.raises(CycleError):
        topo_sort(graph)


def test_cycle_three_nodes():
    graph = {"a": ["b"], "b": ["c"], "c": ["a"]}
    with pytest.raises(CycleError):
        topo_sort(graph)


def test_self_cycle():
    graph = {"a": ["a"]}
    with pytest.raises(CycleError):
        topo_sort(graph)


def test_complex_cycle():
    graph = {
        "x": ["a", "b"],
        "a": ["c"],
        "b": ["d"],
        "c": ["e"],
        "d": ["c"],
        "e": ["b"]  # cycle: b → d → c → e → b
    }
    with pytest.raises(CycleError):
        topo_sort(graph)



# -------------------------
# Extract Dependencies
# -------------------------


def test_simple_dependencies():
    expr = "A + B"
    candidates = {"A", "B", "C"}
    assert set(extract_dependencies(expr, candidates)) == {"A", "B"}


def test_ignores_non_candidates():
    expr = "A + B + UNKNOWN"
    candidates = {"A", "B"}
    assert set(extract_dependencies(expr, candidates)) == {"A", "B"}


def test_ignores_numbers_and_literals():
    expr = "A * 10 + 5"
    candidates = {"A"}
    assert extract_dependencies(expr, candidates) == ["A"]


def test_ignores_functions():
    expr = "max(A - B, 0)"
    candidates = {"A", "B"}
    assert set(extract_dependencies(expr, candidates)) == {"A", "B"}


def test_nested_expression():
    expr = "(A + (B * (C - D)))"
    candidates = {"A", "B", "C", "D"}
    assert set(extract_dependencies(expr, candidates)) == {"A", "B", "C", "D"}


def test_repeated_identifiers():
    expr = "A + A + A"
    candidates = {"A"}
    assert extract_dependencies(expr, candidates) == ["A"]


def test_no_dependencies():
    expr = "42"
    candidates = {"A", "B"}
    assert extract_dependencies(expr, candidates) == []


def test_dependency_order_is_not_guaranteed():
    expr = "B + A"
    candidates = {"A", "B"}
    deps = extract_dependencies(expr, candidates)
    assert set(deps) == {"A", "B"}
    # Order is not important, but ensure it's a list
    assert isinstance(deps, list)


def test_handles_unary_ops():
    expr = "-A + +B"
    candidates = {"A", "B"}
    assert set(extract_dependencies(expr, candidates)) == {"A", "B"}


def test_handles_power_and_other_ops():
    expr = "A**2 + B/3 - C"
    candidates = {"A", "B", "C"}
    assert set(extract_dependencies(expr, candidates)) == {"A", "B", "C"}


def test_handles_attribute_access_but_ignores_it():
    expr = "math.sqrt(A) + B"
    candidates = {"A", "B"}
    # AST sees "math" and "sqrt" as names, but we filter them out
    assert set(extract_dependencies(expr, candidates)) == {"A", "B"}


def test_handles_complex_real_world_expression():
    expr = "max((A - B) / C, D * 1.5)"
    candidates = {"A", "B", "C", "D"}
    assert set(extract_dependencies(expr, candidates)) == {"A", "B", "C", "D"}

# -------------------------
# Build Composite Graph
# -------------------------

def test_build_composite_graph_simple():
    composites = {
        "C": "A + B"
    }
    state = {
        "A": {},
        "B": {},
        "C": {}
    }

    graph = build_composite_graph(composites, state)

    assert set(graph["C"]) == {"A", "B"}


def test_build_composite_graph_multiple():
    composites = {
        "C": "A + B",
        "D": "C * 2"
    }
    state = {
        "A": {},
        "B": {},
        "C": {},
        "D": {}
    }

    graph = build_composite_graph(composites, state)

    assert set(graph["C"]) == {"A", "B"}
    assert set(graph["D"]) == {"C"}


def test_build_composite_graph_ignores_unknown_names():
    composites = {
        "X": "A + B + UNKNOWN"
    }
    state = {
        "A": {},
        "B": {},
        "X": {}
    }

    graph = build_composite_graph(composites, state)

    # UNKNOWN is not in state.keys(), so it must NOT appear
    assert set(graph["X"]) == {"A", "B"}


def test_build_composite_graph_no_dependencies():
    composites = {
        "Z": "42"
    }
    state = {
        "Z": {}
    }

    graph = build_composite_graph(composites, state)

    assert graph == {
        "Z": []
    }
