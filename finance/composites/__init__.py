# Copyright 2026 Rik Essenius
# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.
# File: finance/composites/__init__.py

from .engine import CompositeEngine

__all__ = ["evaluate_composites"]


def evaluate_composites(composites, state):
    """
    Public API for evaluating composites.
    Keeps CompositeEngine internal.
    """
    engine = CompositeEngine(composites, state)
    return engine.evaluate_all()
