# Copyright 2026 Rik Essenius
# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.
# File: src/finance/composites/deps.py

'''TODO re-introduce in scope for V2
import ast
from collections.abc import Iterable

from ..common.introspection import here
from ..common.model import Result


def extract_dependencies(expr: str, candidates: Iterable[str]) -> Result[list[str]]:
    """
    Extract variable names from a composite expression using Python's AST.
    Only returns identifiers that are present in `candidates`.
    """
    context = {"location": here()}

    try:
        tree = ast.parse(expr, mode="eval")
    except SyntaxError as e:
        return Result.fail(f"Syntax error in composite expression '{expr}'", e, meta=context)

    names = set()

    class NameCollector(ast.NodeVisitor):
        def visit_Name(self, node: ast.Name):
            names.add(node.id)

    NameCollector().visit(tree)

    deps = [name for name in names if name in candidates]
    return Result.ok_payload(deps)


class CycleError(Exception):
    """Raised when a cycle is detected in composite dependencies."""

    pass


def topo_sort(graph):
    visited = set()  # nodes fully processed
    active = set()  # nodes in current recursion stack
    order = []

    def visit(node):
        if node in visited:
            return

        if node in active:
            raise CycleError(f"Cycle detected at {node}")

        active.add(node)

        for dep in graph[node]:
            if dep in graph:  # only follow composite→composite edges
                visit(dep)

        active.remove(node)
        visited.add(node)
        order.append(node)

    for node in graph:
        visit(node)

    return order
'''
