# Copyright 2026 Rik Essenius
# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.
# File: tests/test_main.py

def test_main_orchestrator_flow(monkeypatch, capsys):
    from finance import main as main_mod

    fake_config = {
        "general": {"default_interval": 60},
        "symbols": {"spx": {"symbol": "^GSPC"}},
        "composites": {"spread": "t10y - t2y"},
        "secrets": {
            "influx": {"url": "http://x", "db": "finance"},
            "api_keys": {"yahoo": "YKEY"},
        },
    }

    monkeypatch.setattr(main_mod, "load_config", lambda: fake_config)

    state = {"existing": 1}
    monkeypatch.setattr(main_mod, "load_state", lambda: state)

    class FakeWriter:
        def __init__(self, secrets): pass
        def write(self, *a, **kw): pass

    monkeypatch.setattr(main_mod, "InfluxWriter", FakeWriter)

    class FakeFetchController:
        def __init__(self, sources, api_keys, now_provider=None):
            self.sources = sources
            self.api_keys = api_keys
        def fetch_all(self, state):
            return {"spx": (4321, 100)}

    monkeypatch.setattr(main_mod, "FetchController", FakeFetchController)

    monkeypatch.setattr(
        main_mod,
        "evaluate_composites",
        lambda comps, st: {"spread": (10, 200)},
    )

    write_calls = []

    def fake_write_metric(name, value, ts, state, influx_writer):
        write_calls.append((name, value, ts))
        return f"{name}: wrote ({value}/{ts})"

    monkeypatch.setattr(main_mod, "write_metric", fake_write_metric)

    saved_states = []
    monkeypatch.setattr(main_mod, "save_state", lambda s: saved_states.append(s.copy()))

    main_mod.main()

    out = capsys.readouterr().out

    assert ("spx", 4321, 100) in write_calls
    assert ("spread", 10, 200) in write_calls
    assert saved_states == [state]
    assert "spx: wrote (4321/100)" in out
    assert "spread: wrote (10/200)" in out
    assert "Done." in out
    
