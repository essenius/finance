# Copyright 2026 Rik Essenius
# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.
# File: finance/composites/deps.py

import ast


def extract_dependencies(expr: str, candidates) -> list[str]:
    """
    Extract variable names from a composite expression using Python's AST.
    Only returns identifiers that are present in `candidates`.
    """

    tree = ast.parse(expr, mode="eval")
    names = set()

    class NameCollector(ast.NodeVisitor):
        def visit_Name(self, node: ast.Name):
            names.add(node.id)

    NameCollector().visit(tree)

    return [name for name in names if name in candidates]


class CycleError(Exception):
    """Raised when a cycle is detected in composite dependencies."""
    pass

def topo_sort(graph):
    visited = set()          # nodes fully processed
    active = set()           # nodes in current recursion stack
    order = []

    def visit(node):
        if node in visited:
            return

        if node in active:
            raise CycleError(f"Cycle detected at {node}")

        active.add(node)

        for dep in graph[node]:
            if dep in graph:        # only follow composite→composite edges
                visit(dep)

        active.remove(node)
        visited.add(node)
        order.append(node)

    for node in graph:
        visit(node)

    return order

def build_composite_graph(composites, state):
    graph = {}
    for measurement, expr in composites.items():
        deps = extract_dependencies(expr, state.keys())
        graph[measurement] = deps
    return graph
