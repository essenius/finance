# Copyright 2026 Rik Essenius
# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.
# File: tests/test_main.py

from finance.common.log_mixin import LOG_LEVELS, LogMixin


def test_main_orchestrator_flow(monkeypatch, capsys):
    from finance import main as main_mod

    LogMixin.min_level = LOG_LEVELS["debug"]

    fake_config = {
        "buckets": {
            "intraday": "finance_intraday",
            "daily": "finance_daily",
        },
        "general": {"default_interval": 60},
        "assets": {
            "spx": {
                "source": "yahoo",
                "symbol": "^GSPC",
                "tags": {},
                "timeseries": "intraday",
                "fields": ["price"],
                "interval": "10m",
            }
        },
        "composites": {
            "spread": {
                "expression": "t10y - t2y",
                "tags": {},
                "timeseries": "daily",
            }
        },
        "secrets": {
            "influx": {"url": "http://x", "db": "finance"},
            "api_keys": {"yahoo": "YKEY"},
        },
    }

    # Config + state
    monkeypatch.setattr(main_mod, "load_config", lambda: fake_config)

    state = {"existing": 1}
    monkeypatch.setattr(main_mod, "load_state", lambda: state)

    # Fake fetch controller
    class FakeFetchController:
        def __init__(self, sources, api_keys, now_provider=None):
            self.sources = sources
            self.api_keys = api_keys

        def fetch_all(self, state):
            return {"spx": ({"price": 4321}, 100)}

    monkeypatch.setattr(main_mod, "FetchController", FakeFetchController)

    monkeypatch.setattr(
        main_mod,
        "evaluate_composites",
        lambda composites, st: {"spread": ({"value": 10}, 200)},
    )

    # Capture write calls
    write_calls = []

    def fake_write_metric(bucket, measurement, fields, timestamp, state, influx_writer):
        write_calls.append((measurement, fields, timestamp))

        return {
            "ok": False,
            "status": "written",
            "bucket": bucket,
            "measurement": measurement,
            "fields": fields,
            "timestamp": timestamp,
            "reason": "wrote new sample",
        }

    monkeypatch.setattr(main_mod, "write_metric", fake_write_metric)

    # Capture saved state
    saved_states = []
    monkeypatch.setattr(main_mod, "save_state", lambda s: saved_states.append(s.copy()))

    # Run orchestrator
    main_mod.main()

    out = capsys.readouterr().out

    # Assertions
    assert ("spx", {"price": 4321}, 100) in write_calls
    assert ("spread", {"value": 10}, 200) in write_calls

    assert saved_states == [state]
    assert "InfluxWriter initialized | base_url=http://x/write | verify=True" in out
    assert "Done." in out


def test_main_integration(monkeypatch, capsys):
    import finance.main as main_mod

    LogMixin.min_level = LOG_LEVELS["warning"]

    # --- Fake config with a real composite expression ---
    fake_config = {
        "buckets": {
            "intraday": "finance_intraday",
            "daily": "finance_daily",
        },
        "general": {"default_interval": 60},
        "assets": {
            "t10y": {
                "source": "yahoo",
                "symbol": "^TNX",
                "tags": {},
                "timeseries": "daily",
                "fields": ["value"],
                "interval": "1d",
            },
            "t2y": {
                "source": "yahoo",
                "symbol": "^IRX",
                "tags": {},
                "timeseries": "daily",
                "fields": ["value"],
                "interval": "1d",
            },
        },
        "composites": {
            "spread": {
                "expression": "t10y - t2y",
                "tags": {},
                "timeseries": "daily",
            }
        },
        "secrets": {
            "influx": {"url": "http://x", "db": "finance"},
            "api_keys": {"yahoo": "YKEY"},
        },
    }

    monkeypatch.setattr(main_mod, "load_config", lambda: fake_config)

    # --- Fake state ---
    state = {}
    monkeypatch.setattr(main_mod, "load_state", lambda: state)

    # --- Fake InfluxWriter ---
    class FakeWriter:
        def __init__(self, secrets):
            pass

    monkeypatch.setattr(main_mod, "InfluxWriter", FakeWriter)

    # --- Fake fetch controller returning real asset values ---
    class FakeFetchController:
        def __init__(self, sources, api_keys, now_provider=None):
            pass

        def fetch_all(self, state):
            return {
                "t10y": ({"value": 4.0}, 100),
                "t2y": ({"value": 3.5}, 100),
            }

    monkeypatch.setattr(main_mod, "FetchController", FakeFetchController)

    # --- Capture write_metric calls ---
    writes = []

    def fake_write_metric(bucket, measurement, fields, ts, state, influx_writer):
        # mimic real state update
        entry = state.setdefault(measurement, {})
        entry["fields"] = fields
        entry["last_timestamp"] = ts
        writes.append((bucket, measurement, fields, ts))
        return f"{measurement}: wrote ({fields}/{ts})"

    monkeypatch.setattr(main_mod, "write_metric", fake_write_metric)

    # --- Capture saved state ---
    saved_states = []
    monkeypatch.setattr(main_mod, "save_state", lambda s: saved_states.append(s.copy()))

    # --- Run orchestrator ---
    main_mod.main()

    out = capsys.readouterr().out
    err = capsys.readouterr().err

    # --- Assertions ---
    # Asset writes
    assert ("finance_daily", "t10y", {"value": 4.0}, 100) in writes
    assert ("finance_daily", "t2y", {"value": 3.5}, 100) in writes

    # Composite write (real CompositeEngine)
    assert ("finance_daily", "spread", {"value": 0.5}, 100) in writes

    # State saved
    assert saved_states == [state]

    # Output
    assert out == ""
    assert err == ""
