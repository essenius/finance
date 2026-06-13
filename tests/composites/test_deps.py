# Copyright 2026 Rik Essenius
# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.
# File: tests/composites/test_deps.py

import pytest

from finance.composites.deps import CycleError, extract_dependencies, topo_sort

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
    graph = {"d": ["b", "c"], "b": ["a"], "c": ["a"], "a": []}
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
    graph = {"c": ["a", "b", "external"], "a": [], "b": []}
    result = topo_sort(graph)
    assert result.index("a") < result.index("c")
    assert result.index("b") < result.index("c")


def test_wide_graph():
    graph = {"z": ["a", "b", "c", "d", "e"], "a": [], "b": [], "c": [], "d": [], "e": []}
    result = topo_sort(graph)
    for parent in ["a", "b", "c", "d", "e"]:
        assert result.index(parent) < result.index("z")


def test_deep_graph():
    graph = {"n5": ["n4"], "n4": ["n3"], "n3": ["n2"], "n2": ["n1"], "n1": []}
    assert topo_sort(graph) == ["n1", "n2", "n3", "n4", "n5"]


def test_unordered_input_keys():
    graph = {"c": ["b"], "a": [], "b": ["a"]}
    assert topo_sort(graph) == ["a", "b", "c"]


# -------------------------
#  Topo Sort Cycles
# -------------------------


@pytest.mark.parametrize(
    "graph",
    [
        # Two‑node cycle
        {"a": ["b"], "b": ["a"]},
        # Three‑node cycle
        {"a": ["b"], "b": ["c"], "c": ["a"]},
        # Self‑cycle
        {"a": ["a"]},
        # Complex cycle: b → d → c → e → b
        {
            "x": ["a", "b"],
            "a": ["c"],
            "b": ["d"],
            "c": ["e"],
            "d": ["c"],
            "e": ["b"],
        },
    ],
)
def test_topo_sort_cycles(graph):
    with pytest.raises(CycleError):
        topo_sort(graph)


# -------------------------
# Extract Dependencies
# -------------------------


@pytest.mark.parametrize(
    "expr, candidates, expected",
    [
        ("A + B", {"A", "B", "C"}, {"A", "B"}),  # simple
        ("A + B + UNKNOWN", {"A", "B"}, {"A", "B"}),  # non-candidates
        ("A * 10 + 5", {"A"}, {"A"}),  # numbers and literals
        ("max(A - B, 0)", {"A", "B"}, {"A", "B"}),  # ignore functions
        ("(A + (B * (C - D)))", {"A", "B", "C", "D"}, {"A", "B", "C", "D"}),  # nested expression
        ("A + A + A", {"A"}, {"A"}),  # repeated ID
        ("42", {"A", "B"}, set()),  # no dependencies
        ("B + A", {"A", "B"}, {"A", "B"}),  # order not guaranteed
        ("-A + +B", {"A", "B"}, {"A", "B"}),  # handles unary ops
        ("A**2 + B/3 - C", {"A", "B", "C"}, {"A", "B", "C"}),  # handles power and other ops
        ("math.sqrt(A) + B", {"A", "B"}, {"A", "B"}),  # filters out math and sqrt
        ("max((A - B) / C, D * 1.5)", {"A", "B", "C", "D"}, {"A", "B", "C", "D"}),  # complex expression
    ],
)
def test_extract_dependencies_ok(expr, candidates, expected):
    result = extract_dependencies(expr, candidates)
    assert result.ok
    assert set(result.payload) == expected


@pytest.mark.parametrize(
    "expr",
    [
        "A +",  # trailing operator
        "(",  # incomplete
        "A * * B",  # invalid operator sequence
        "A + (B * )",  # missing operand
    ],
)
def test_extract_dependencies_syntax_error(expr):
    result = extract_dependencies(expr, {"A", "B"})
    assert not result.ok
    assert "Syntax error" in result.reason


# -------------------------
# Build Composite Graph
# -------------------------


def test_composite_graph_equivalent_behavior():
    composites = {"C": "A + B", "D": "C * 2"}
    state = {"A": {}, "B": {}, "C": {}, "D": {}}

    # Extract deps using the new Result API
    deps = {}
    for name, expr in composites.items():
        result = extract_dependencies(expr, state.keys())
        assert result.ok, f"Unexpected parse error: {result.reason}"
        deps[name] = set(result.payload)

    # Only composite→composite edges matter
    graph = {name: [dep for dep in deps[name] if dep in composites] for name in composites}

    order = topo_sort(graph)

    assert order == ["C", "D"]
