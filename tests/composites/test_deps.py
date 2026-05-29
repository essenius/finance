# Copyright 2026 Rik Essenius
# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.
# File: tests/composites/test_deps.py

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
    deps, err = extract_dependencies(expr, candidates)
    assert err is None
    assert set(deps) == expected


@pytest.mark.parametrize(
    "expr",
    [
        "A +",  # trailing operator
        "(",  # incomplete
        "A * * B",  # invalid operator sequence
        "A + (B * )",  # missing operand
    ],
)
def test_extract_dependencies_syntax_error(expr, capsys):
    deps, err = extract_dependencies(expr, {"A", "B"})
    assert deps == []
    assert "Syntax error" in err


# -------------------------
# Build Composite Graph
# -------------------------


@pytest.mark.parametrize(
    "composites, state, expected",
    [
        # Simple
        ({"C": "A + B"}, {"A": {}, "B": {}, "C": {}}, {"C": {"A", "B"}}),
        # Multiple
        (
            {"C": "A + B", "D": "C * 2"},
            {"A": {}, "B": {}, "C": {}, "D": {}},
            {"C": {"A", "B"}, "D": {"C"}},
        ),
        # Composite depends on composite (your added case)
        ({"C": "A + B", "D": "C * 2"}, {"A": {}, "B": {}, "C": {}, "D": {}}, {"C": {"A", "B"}, "D": {"C"}}),
        # Unknown names ignored
        (
            {"X": "A + B + UNKNOWN"},
            {"A": {}, "B": {}, "X": {}},
            {"X": {"A", "B"}},
        ),
        # No dependencies
        (
            {"Z": "42"},
            {"Z": {}},
            {"Z": set()},
        ),
    ],
)
def test_build_composite_graph(composites, state, expected):
    graph, errors = build_composite_graph(composites, state)

    # Graph correctness
    for key, deps in expected.items():
        assert set(graph[key]) == deps

    # No errors expected in these cases
    assert errors == {}


@pytest.mark.parametrize(
    "expr",
    ["A +", "(", "A * * B", "A + (B * )"],
)
def test_build_composite_graph_syntax_errors(expr):
    composites = {"C": expr}
    state = {"A": {}, "B": {}, "C": {}}

    graph, errors = build_composite_graph(composites, state)

    assert graph["C"] == []
    assert "Syntax error" in errors["C"]
