# Copyright 2026 Rik Essenius
# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.
# File: tests/test_main.py

from unittest.mock import Mock

import pytest

from finance.common.log_mixin import LOG_LEVELS, LogMixin


def test_main_orchestrator_flow(monkeypatch, tmp_path, caplog):
    from finance import main as main_mod

    caplog.set_level("DEBUG")

    fake_config = {
        "buckets": {
            "intraday": "finance_intraday",
            "daily": "finance_daily",
        },
        "general": {"default_interval": 60},
        "assets": {
            "spx": {
                "provider": "yahoo",
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
        "paths": {
            "wal": tmp_path / "wal.jsonl",
            "state": tmp_path / "state.json",
        },
    }

    monkeypatch.setattr(main_mod, "load_config", lambda: fake_config)

    # Fake WAL
    fake_wal = Mock()
    monkeypatch.setattr(main_mod, "JsonlWAL", lambda path: fake_wal)

    # Fake State
    fake_state_data = {"existing": 1}
    fake_state = Mock()
    fake_state.return_value = fake_state
    fake_state.data = fake_state_data

    monkeypatch.setattr(main_mod, "State", fake_state)

    # Fake fetch controller
    class FakeFetchController:
        def __init__(self, sources, api_keys, now_provider=None):
            pass

        def fetch_all(self, state):
            return {"spx": ({"price": 4321}, 100)}

    monkeypatch.setattr(main_mod, "FetchController", FakeFetchController)

    # Fake composite evaluator
    monkeypatch.setattr(
        main_mod,
        "evaluate_composites",
        lambda composites, st: {"spread": ({"value": 10}, 200)},
    )

    # Capture write_metric calls
    write_calls = []

    def fake_write_metric(bucket, measurement, fields, timestamp, state):
        write_calls.append((bucket, measurement, fields, timestamp))
        return {"ok": True}

    monkeypatch.setattr(main_mod, "write_metric", fake_write_metric)

    # Run orchestrator
    main_mod.main()

    fake_state.save.assert_called_once()
    assert fake_state.data == {"existing": 1}

    assert ("finance_intraday", "spx", {"price": 4321}, 100) in write_calls
    assert ("finance_daily", "spread", {"value": 10}, 200) in write_calls

    assert "Done." in caplog.text

    # Capture write_metric calls
    write_calls = []

    def fake_write_metric(bucket, measurement, fields, timestamp, state):
        write_calls.append((bucket, measurement, fields, timestamp))
        return {"ok": True}

    monkeypatch.setattr(main_mod, "write_metric", fake_write_metric)

    # Run orchestrator
    main_mod.main()


    # Assertions
    assert ("finance_intraday", "spx", {"price": 4321}, 100) in write_calls
    assert ("finance_daily", "spread", {"value": 10}, 200) in write_calls

    assert "Done." in caplog.text


def test_main_integration(monkeypatch, tmp_path, caplog):
    import finance.main as main_mod

    LogMixin.min_level = LOG_LEVELS["warning"]

    fake_config = {
        "buckets": {
            "intraday": "finance_intraday",
            "daily": "finance_daily",
        },
        "general": {"default_interval": 60},
        "assets": {
            "t10y": {
                "provider": "yahoo",
                "symbol": "^TNX",
                "tags": {},
                "timeseries": "daily",
                "fields": ["value"],
                "interval": "1d",
            },
            "t2y": {
                "provider": "yahoo",
                "symbol": "^IRX",
                "tags": {},
                "timeseries": "daily",
                "fields": ["value"],
                "interval": "1d",
            },
            "boom": {
                "provider": "yahoo",
                #"symbol": "^IRX",
                #"tags": {},
                "timeseries": "daily",
                #"fields": ["value"],
                #"interval": "1d",
            },
        },
        "composites": {
            "spread": {
                "expression": "t10y - t2y",
                "tags": {},
                "timeseries": "daily",
            },
            "bad_composite": {
                "expression": "t10y + boom",   # or any expression, it won't be evaluated
                "tags": {},
                "timeseries": "daily",
            },
        },
        "secrets": {
            "influx": {"url": "http://x", "db": "finance"},
            "api_keys": {"yahoo": "YKEY"},
        },
        "paths": {
            "wal": tmp_path / "wal.jsonl",
            "state": tmp_path / "state.json",
        },
    }

    monkeypatch.setattr(main_mod, "load_config", lambda: fake_config)

    # Fake WAL
    fake_wal = Mock()
    monkeypatch.setattr(main_mod, "JsonlWAL", lambda path: fake_wal)


    class FakeState(dict):
        def __init__(self, ts, wal, path):
            super().__init__()
            self.data = self  # for compatibility with write_metric

        def save(self):
            pass

    monkeypatch.setattr(main_mod, "State", FakeState)

    # Fake fetch controller
    class FakeFetchController:
        def __init__(self, sources, api_keys, now_provider=None):
            pass

        def fetch_all(self, state):
            return {
                "t10y": ({"value": 4.0}, 100),
                "t2y": ({"value": 3.5}, 100),
                "boom": ({"value": 1}, 100),
            }

    monkeypatch.setattr(main_mod, "FetchController", FakeFetchController)

    writes = []

    def fake_write_metric(bucket, measurement, fields, ts, state):
        # Simulate a failure for one specific metric
        if measurement in ("boom", "bad_composite"):
            writes.append((bucket, measurement, fields, ts))
            return {"ok": False, "status": "error", "reason": "simulated failure"}

        entry = state.setdefault(measurement, {})
        entry["fields"] = fields
        entry["last_timestamp"] = ts
        writes.append((bucket, measurement, fields, ts))
        return {"ok": True}

    monkeypatch.setattr(main_mod, "write_metric", fake_write_metric)

    # Inject a composite failure to ensure failures+=1 is exercised
    def fake_evaluate_composites(composites, st):
        return {
            "spread": ({"value": 0.5}, 100),
            "bad_composite": ({"value": 999}, 100),
        }

    monkeypatch.setattr(main_mod, "evaluate_composites", fake_evaluate_composites)

    caplog.set_level("ERROR")
    with pytest.raises(SystemExit) as excinfo:
        main_mod.main()
    assert excinfo.value.code == 1

    assert "write failures" in caplog.text

    assert ("finance_daily", "t10y", {"value": 4.0}, 100) in writes
    assert ("finance_daily", "t2y", {"value": 3.5}, 100) in writes
    assert ("finance_daily", "spread", {"value": 0.5}, 100) in writes
