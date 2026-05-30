# Copyright 2026 Rik Essenius
# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.
# File: finance/composites/engine.py

import re

from finance.common.log_mixin import LogMixin

from .deps import extract_dependencies, topo_sort

IDENTIFIER_RE = re.compile(r"\b([A-Za-z_][A-Za-z0-9_]*)\b")


class MetricProxy:
    """Simple object exposing metric fields as attributes."""

    def __init__(self, fields: dict):
        self.__dict__.update(fields)


class CompositeEngine(LogMixin):
    """Evaluate composites with implicit timeseries resolution and dependency ordering."""

    def __init__(self, composites: dict, state: dict):
        """
        composites: dict[name] -> {
            "expression": str,
            "measurement": str,
            "timeseries": str,
            "tags": dict,
        }
        state: dict[metric_name] -> {
            "fields": dict[field_name] -> value,
            "last_timestamp": int,
        }
        """
        self.composites = composites
        self.state = state

        # Map composite name -> metric name (with timeseries suffix)
        self.composite_to_metric = {}
        for name, cfg in self.composites.items():
            timeseries = cfg.get("timeseries", "daily")
            cfg["timeseries"] = timeseries  # normalize in-place so rest of engine can rely on it
            self.composite_to_metric[name] = f"{name}_{timeseries}"

        self.graph = self._build_graph()
        self.order = topo_sort(self.graph)

    # ------------------------------------------------------------------ #
    # Dependency graph (composite -> composite)
    # ------------------------------------------------------------------ #

    # NOTE: We intentionally have two different dependency graph builders:
    #
    # 1) deps.build_composite_graph()
    #    - Extracts *metric* dependencies (composite → metric)
    #    - Used for evaluation and timestamp propagation
    #    - Filters identifiers using state.keys()
    #    - Returns (graph, errors)
    #
    # 2) CompositeEngine._build_graph()
    #    - Extracts *composite* dependencies (composite → composite)
    #    - Used only for topological sorting and cycle detection
    #    - Filters identifiers using composites.keys()
    #
    # These graphs serve different purposes and cannot be merged.
    # The topo-sort graph must ignore metric names, while the evaluation
    # graph must include them. Keeping them separate avoids subtle bugs.

    def _build_graph(self):
        graph = {}
        for name, cfg in self.composites.items():
            expr = cfg["expression"]
            deps, err = extract_dependencies(expr, self.composites.keys())
            if err:
                self.error(f"Composite {name}: {err}")
                deps = []
            graph[name] = deps
        return graph

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
        if candidate in self.state:
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

        def repl(match):
            identifier = match.group(1)

            # Not a known metric → leave as-is
            if identifier not in self.state:
                return identifier

            # If the next character is '.', this is metric.field → leave as-is
            end = match.end(1)
            if end < len(expression) and expression[end] == ".":
                return identifier

            # Bare metric → metric.value
            return f"{identifier}.value"

        return IDENTIFIER_RE.sub(repl, expression)

    # ------------------------------------------------------------------ #
    # Namespace for eval()
    # ------------------------------------------------------------------ #
    def _build_namespace(self) -> dict:
        """
        Build a namespace mapping metric names to MetricProxy objects.
        Example: gold_daily.high → state["gold_daily"]["fields"]["high"]
        """
        namespace = {}
        for metric_name, entry in self.state.items():
            namespace[metric_name] = MetricProxy(entry.get("fields", {}))
        return namespace

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #
    def evaluate_all(self) -> dict:
        """
        Evaluate all composites in dependency order.

        Returns:
            dict[name] -> (fields_dict, timestamp)
        """
        results = {}
        namespace = self._build_namespace()

        for name in self.order:
            cfg = self.composites[name]
            raw_expression = cfg["expression"]
            timeseries = cfg["timeseries"]

            # 1) Rewrite identifiers: composite names + implicit timeseries
            rewritten_expression = self._rewrite_expression(raw_expression, timeseries)

            # 2) Add default '.value' for bare metric references
            rewritten_expression = self._add_default_field(rewritten_expression)

            # 3) Evaluate safely
            try:
                value = eval(rewritten_expression, {"__builtins__": {}}, namespace)
            except Exception as e:
                self.error(f"Composite {name} failed: {e}")
                continue

            # 4) Determine timestamp based on metric dependencies
            #    err cannot be set, since the eval function would have failed otherwise.
            metric_dependencies, _ = extract_dependencies(rewritten_expression, self.state.keys())

            # Collect timestamps of metric dependencies
            timestamps = [
                self.state[m]["last_timestamp"]
                for m in metric_dependencies
                if self.state[m]["last_timestamp"] is not None
            ]

            if timestamps:
                # Use timestamps of actual dependencies
                timestamp = max(timestamps)
            else:
                # No metric dependencies → use freshest real metric timestamp in state
                all_ts = [
                    entry.get("last_timestamp")
                    for entry in self.state.values()
                    if entry.get("last_timestamp") is not None
                ]
                timestamp = max(all_ts) if all_ts else 0

            # 5) Store result under composite name
            results[name] = ({"value": value}, timestamp)

            # 6) Feed result back into state + namespace under metric name
            metric_name = self.composite_to_metric[name]
            self.state[metric_name] = {
                "fields": {"value": value},
                "last_timestamp": timestamp,
            }
            namespace[metric_name] = MetricProxy({"value": value})

        return results
