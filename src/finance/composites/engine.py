# Copyright 2026 Rik Essenius
# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.
# File: src/finance/composites/engine.py

'''
TODO re-introduce in scope vor V2
from __future__ import annotations

import ast
import re
from collections.abc import Iterable

from ..common.introspection import here
from ..common.model import DAILY, RESOLUTION, FetchPoint, FetchResult, MeasurementResult, Result
from ..state.state import State
from .deps import CycleError, extract_dependencies, topo_sort

IDENTIFIER_RE = re.compile(r"\b([A-Za-z_][A-Za-z0-9_]*)\b")


class MetricProxy:
    """Simple object exposing metric fields as attributes."""

    def __init__(self, fields: dict):
        self.__dict__.update(fields)


class DefaultFieldTransformer(ast.NodeTransformer):
    def __init__(self, metric_names: set[str]):
        self.metric_names = metric_names

    def visit_Attribute(self, node: ast.Attribute):
        # IMPORTANT: do NOT recurse into .value
        # This prevents transforming the base of `gold.high`
        return node

    def visit_Name(self, node: ast.Name):
        # Only bare metric identifiers get `.value`
        if node.id in self.metric_names:
            return ast.Attribute(value=node, attr="value", ctx=node.ctx)
        return node


class CompositeEngine:
    """Evaluate composites with implicit timeseries resolution and dependency ordering."""

    def __init__(self, composites: dict, state: State):
        """
        composites: dict[name] -> {
            "expression": str,
            "measurement": str,
            RESOLUTION: str,
            "tags": dict,
        }
        """
        self.composites = composites
        self.state = state

        # Map composite name -> metric name (with timeseries suffix)
        self.composite_to_metric = {}
        for name, cfg in self.composites.items():
            timeseries = cfg.get(RESOLUTION, DAILY)
            cfg[RESOLUTION] = timeseries  # normalize in-place so rest of engine can rely on it
            self.composite_to_metric[name] = f"{name}_{timeseries}"

        # These are filled in by build()
        self.graph = {}
        self.order = []

    @classmethod
    def build(cls, composites: dict, state: State) -> Result[CompositeEngine]:
        context = {"location": here()}
        engine = cls(composites, state)

        graph_result = engine._build_graph()
        if not graph_result.ok:
            return graph_result

        try:
            order = topo_sort(graph_result.payload)
        except CycleError as exc:
            return Result.fail(reason="Error in topo_sort", error=exc, meta=context)

        engine.graph = graph_result.payload
        engine.order = order
        return Result.ok_payload(engine)

    # ------------------------------------------------------------------ #
    # Dependency graph (composite -> composite)
    # ------------------------------------------------------------------ #

    def _build_graph(self) -> Result[dict]:
        graph = {}
        for name, cfg in self.composites.items():
            expr = cfg["expression"]
            deps_result = extract_dependencies(expr, self.composites.keys())
            if not deps_result.ok:
                return deps_result
            graph[name] = deps_result.payload
        return Result.ok_payload(graph)

    # ------------------------------------------------------------------ #
    # Identifier resolution (composite/metric names, implicit timeseries)
    # ------------------------------------------------------------------ #
    def _resolve_identifier(self, identifier: str, timeseries: str) -> str:
        """
        Resolve an identifier inside a composite expression.

        Rules:
        - If identifier is a composite name, map to its metric name (name_timeseries).
        - Else, if identifier already ends with _<timeseries>, leave as-is (explicit override).
        - Else, if identifier_<timeseries> exists in state, expand to identifier_<timeseries>.
        - Else, leave identifier unchanged (could be a function name, etc.).
        """
        # Composite name → metric name
        if identifier in self.composites:
            return self.composite_to_metric[identifier]

        suffix = f"_{timeseries}"
        if identifier.endswith(suffix):
            return identifier

        candidate = f"{identifier}{suffix}"
        if candidate in self.state.series:
            return candidate

        return identifier

    def _rewrite_expression(self, expression: str, timeseries: str) -> str:
        """Rewrite identifiers to include implicit timeseries suffix and composite→metric mapping."""

        def repl(match):
            identifier = match.group(1)
            return self._resolve_identifier(identifier, timeseries)

        return IDENTIFIER_RE.sub(repl, expression)

    def _add_default_field(self, expression: str) -> str:
        """
        Add '.value' to bare metric references.

        Example:
            A_daily + B_daily → A_daily.value + B_daily.value
            gold_daily.high stays gold_daily.high
        """

        tree = ast.parse(expression, mode="eval")
        metric_names = set(self.state.series.keys()) | set(self.composite_to_metric.values())
        transformer = DefaultFieldTransformer(metric_names)
        new_tree = transformer.visit(tree)
        ast.fix_missing_locations(new_tree)
        return ast.unparse(new_tree)

    # ------------------------------------------------------------------ #
    # Namespace for eval()
    # ------------------------------------------------------------------ #
    def _build_namespace(self) -> dict:
        """
        Build a namespace mapping metric names to MetricProxy objects.
        Example: gold_daily.high → state["gold_daily"]["fields"]["high"]
        """
        namespace = {}
        for metric_name, entry in self.state.iter_series_state():
            fields = entry.get("fields", {})
            namespace[metric_name] = MetricProxy(fields)
        return namespace

    # ------------------------------------------------------------------ #
    # Single composite evaluation
    # ------------------------------------------------------------------ #

    def _evaluate_single(self, name: str, namespace: dict) -> MeasurementResult[FetchPoint]:
        context = {"location": here()}
        cfg = self.composites[name]
        raw_expression = cfg["expression"]
        timeseries = cfg[RESOLUTION]

        # 1) Rewrite identifiers
        rewritten = self._rewrite_expression(raw_expression, timeseries)

        # 2) Add default '.value'
        rewritten = self._add_default_field(rewritten)

        # 3) Evaluate safely
        try:
            value = eval(rewritten, {"__builtins__": {}}, namespace)
        except Exception as e:
            return MeasurementResult.fail(name, f"Evaluating composite {name} failed", e, meta=context)

        # 4) Determine timestamp

        deps_result = extract_dependencies(rewritten, self.state.series.keys())
        # cannot fail if the eval succeeded

        metric_dependencies = deps_result.payload

        timestamps = [ts for m in metric_dependencies if (ts := self.state.get_last_timestamp(m)) is not None]

        if timestamps:
            timestamp = max(timestamps)
        else:
            # No metric deps → use freshest real metric timestamp
            all_timestamps = [
                entry["last_timestamp"]
                for _, entry in self.state.iter_series_state()
                if entry.get("last_timestamp") is not None
            ]
            timestamp = max(all_timestamps) if all_timestamps else 0

        point = FetchPoint(fields={"value": value}, timestamp=timestamp)
        return MeasurementResult.ok_payload(name, point)

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #

    def evaluate_incrementally(self) -> Iterable[FetchResult]:
        """
        Evaluate composites in dependency order, yielding results one by one.
        Orchestrator ingests each result immediately.
        """
        namespace = self._build_namespace()

        for name in self.order:
            single = self._evaluate_single(name, namespace)

            if not single.ok:
                # propagate failure for this composite, but continue with others
                yield single
                continue

            point = single.payload
            metric_name = self.composite_to_metric[name]

            # Update state
            self.state.update_composite(metric_name, point.fields, point.timestamp)

            # Update namespace
            namespace[metric_name] = MetricProxy(point.fields)

            yield FetchResult.ok_payload(name, [point])
'''
