# Copyright 2026 Rik Essenius
# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.
# File: tests/composites/test_composite_api.py


def test_evaluate_composites_calls_engine(monkeypatch):
    import finance.composites as comp_mod

    calls = []

    class FakeEngine:
        def __init__(self, comps, state):
            calls.append(("init", comps, state))

        def evaluate_all(self):
            calls.append(("eval",))
            return {"C": ({"value": 5}, 100)}

    # Patch the symbol used by the façade
    monkeypatch.setattr(comp_mod, "CompositeEngine", FakeEngine)

    result = comp_mod.evaluate_composites({"C": {}}, {"state": 1})

    assert result == {"C": ({"value": 5}, 100)}
    assert calls == [
        ("init", {"C": {}}, {"state": 1}),
        ("eval",),
    ]
