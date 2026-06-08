# Copyright 2026 Rik Essenius
# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.
# File: tests/test_main.py

from unittest.mock import Mock

import pytest

from finance.common.model import FetchPoint, MeasurementResult, Result, TimeseriesWrite

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class FakeFetchController:
    """Simulates fetch_incrementally() producing FetchResult objects."""

    def __init__(self, outputs):
        # outputs = [(measurement, fields, timestamp), ...]
        self.outputs = outputs

    def fetch_incrementally(self, state):
        for measurement, fields, ts in self.outputs:
            fp = FetchPoint(fields=fields, timestamp=ts)
            # FetchResult = MeasurementResult[list[FetchPoint]]
            yield MeasurementResult.ok_payload(measurement, [fp])


class FakeState:
    instance = None

    def __init__(self, *args, **kwargs):
        self.calls = []
        self.saved = False
        self.bucket_for = kwargs.get("bucket_for")
        FakeState.instance = self

    def save(self):
        self.saved = True

    def ingest(self, write):
        self.calls.append(write)
        return Result.ok_payload(None)


class FailingState(FakeState):
    instance = None

    def __init__(self, *args, **kwargs):
        FailingState.instance = self

    """State that fails ingest for testing failure path."""

    def ingest(self, write: TimeseriesWrite):
        return Result.fail(write.measurement, "simulated failure")


class FakeInfluxBackend:
    def write(self, *a, **kw):
        pass

    def read(self, *a, **kw):
        return []


def make_influx_backend(monkeypatch):
    fake_backend = FakeInfluxBackend()

    def fake_from_secrets(secrets):
        return Result.ok_payload(fake_backend)

    monkeypatch.setattr("finance.timeseries.influx.InfluxBackend.from_secrets", fake_from_secrets)
    monkeypatch.setattr("finance.timeseries.influx.InfluxBackend", lambda *a, **kw: fake_backend)
    return fake_backend


def make_composite_engine(monkeypatch, outputs, fail=None):
    """
    outputs = [
        ("spread", {"value": 123}, 500),
        ...
    ]
    """

    class FakeCompositeEngine:
        def __init__(self, outputs, fail):
            self.outputs = outputs
            self.fail = fail

        def evaluate_incrementally(self):
            for measurement, fields, ts in self.outputs:
                if self.fail:
                    yield MeasurementResult.fail(measurement, "simulated failure")
                else:
                    fp = FetchPoint(fields=fields, timestamp=ts)
                    yield MeasurementResult.ok_payload(measurement, [fp])

    def fake_build(*_):
        if fail == "build":
            return Result.fail("simulated failure")
        else:
            return Result.ok_payload(FakeCompositeEngine(outputs, fail == "eval"))

    # Patch the *method*, not the class
    monkeypatch.setattr("finance.composites.engine.CompositeEngine.build", fake_build)


# ---------------------------------------------------------------------------
# Test: Happy path
# ---------------------------------------------------------------------------


def test_main_happy_path(monkeypatch, tmp_path, caplog):
    import finance.main as main_mod

    caplog.set_level("DEBUG")

    # Fake config
    fake_config = {
        "paths": {
            "wal": tmp_path / "wal.jsonl",
            "state": tmp_path / "state.json",
        },
        "secrets": {
            "influx": {"url": "http://x", "db": "finance"},
            "api_keys": {"yahoo": "YKEY"},
        },
        "assets": {"spx": {"tags": {"m": "s"}, "timeseries": "intraday", "bucket": "finance_intraday"}},
        "composites": {
            "spread": {
                "tags": {"c": "s"},
                "timeseries": "daily",
            }
        },
        "buckets": {
            "intraday": "finance_intraday",
            "daily": "finance_daily",
        },
    }

    monkeypatch.setattr(main_mod, "load_config", lambda: Result.ok_payload(fake_config))
    monkeypatch.setattr(main_mod, "JsonlWAL", lambda path: Mock())
    make_influx_backend(monkeypatch)
    monkeypatch.setattr(main_mod, "State", FakeState)

    fetch_outputs = [("spx", {"price": 4321}, 100)]
    monkeypatch.setattr(main_mod, "FetchController", lambda assets, keys: FakeFetchController(fetch_outputs))

    composite_outputs = [("spread", {"value": 10}, 200)]
    make_composite_engine(monkeypatch, composite_outputs)

    # Run main
    main_mod.main()
    state = FakeState.instance

    # Assertions
    assert state is not None
    assert state.saved is True
    assert len(state.calls) == 2

    w1, w2 = state.calls

    assert w1.measurement == "spx"
    assert w1.fields == {"price": 4321}
    assert w1.timestamp == 100
    assert w1.bucket == "finance_intraday"

    assert w2.measurement == "spread"
    assert w2.fields == {"value": 10}
    assert w2.timestamp == 200
    assert w2.bucket == "finance_daily"

    assert "Finance version: " in caplog.text
    assert "INFO | Done." in caplog.text


# ---------------------------------------------------------------------------
# Test: Failure path
# ---------------------------------------------------------------------------


def test_main_failure(monkeypatch, tmp_path, caplog):
    import finance.main as main_mod

    caplog.set_level("ERROR")

    fake_config = {
        "paths": {
            "wal": tmp_path / "wal.jsonl",
            "state": tmp_path / "state.json",
        },
        "secrets": {
            "influx": {"url": "http://x", "db": "finance"},
            "api_keys": {"yahoo": "YKEY"},
        },
        "assets": {"boom": {"tags": {}, "timeseries": "daily", "bucket": "finance_daily"}},
        "composites": {},
        "buckets": {
            "daily": "finance_daily",
        },
    }

    monkeypatch.setattr(main_mod, "load_config", lambda: Result.ok_payload(fake_config))
    monkeypatch.setattr(main_mod, "JsonlWAL", lambda path: Mock())

    make_influx_backend(monkeypatch)

    monkeypatch.setattr(main_mod, "State", FailingState)

    # Fake fetch controller producing one metric
    fetch_outputs = [("boom", {"value": 1}, 100)]
    monkeypatch.setattr(main_mod, "FetchController", lambda assets, keys: FakeFetchController(fetch_outputs))

    # No composites
    make_composite_engine(monkeypatch, [])

    with pytest.raises(SystemExit) as excinfo:
        main_mod.main()

    assert excinfo.value.code == 1
    assert "ERROR | reason=boom | error=simulated failure" in caplog.text
    assert "ERROR | Fetch completed with 1 failures" in caplog.text


def test_main_bucket_for_closure(monkeypatch, tmp_path, caplog):
    import finance.main as main_mod

    # Minimal config that main() expects
    fake_config = {
        "assets": {},
        "composites": {"spread": {"tags": {}, "timeseries": "daily"}},
        "measurements": {"spread": {"bucket": "daily"}},
        "paths": {"state": tmp_path / "state.json", "wal": tmp_path / "wal.jsonl"},
        "secrets": {"influx": {"url": "x", "db": "y"}},
        "buckets": {"daily": "d", "intraday": "i"},
    }

    monkeypatch.setattr(main_mod, "load_config", lambda: Result.ok_payload(fake_config))
    make_influx_backend(monkeypatch)
    monkeypatch.setattr(main_mod, "State", FakeState)
    monkeypatch.setattr(main_mod, "FetchController", lambda assets, keys: FakeFetchController([]))
    make_composite_engine(monkeypatch, [("spread", {"value": 10}, 200)], fail="eval")
    with pytest.raises(SystemExit) as se:
        main_mod.main()

    # main exits with 1 because of composite failure
    assert se.value.code == 1

    assert " reason=simulated failure " in caplog.text
    assert "Composite evaluation completed with 1 failures" in caplog.text

    state = FakeState.instance
    assert state is not None
    assert state.bucket_for is not None
    # execute the closure
    assert state.bucket_for("spread") == "daily"


def test_main_composite_failure_increments(monkeypatch, tmp_path, caplog):
    import finance.main as main_mod

    fake_config = {
        "assets": {},
        "composites": {"spread": {"tags": {}, "timeseries": "daily"}},
        "measurements": {"spread": {"bucket": "daily"}},
        "paths": {"state": tmp_path / "state.json", "wal": tmp_path / "wal.jsonl"},
        "secrets": {"influx": {"url": "x", "db": "y"}},
        "buckets": {"daily": "d", "intraday": "i"},
    }
    monkeypatch.setattr(main_mod, "load_config", lambda: Result.ok_payload(fake_config))
    make_influx_backend(monkeypatch)
    monkeypatch.setattr(main_mod, "State", FakeState)
    monkeypatch.setattr(main_mod, "FetchController", lambda assets, keys: FakeFetchController([]))
    make_composite_engine(monkeypatch, [("spread", {"value": 10}, 200)], fail="eval")

    caplog.set_level("ERROR")

    with pytest.raises(SystemExit) as se:
        main_mod.main()

    assert se.value.code == 1
    assert "ERROR | reason=simulated failure" in caplog.text
    assert "ERROR | Composite evaluation completed with 1 failures" in caplog.text


def test_main_unwrap_error_triggers_exit_2(monkeypatch, tmp_path, caplog):
    import finance.main as main_mod
    from finance.common.model import Result

    # Minimal valid config
    fake_config = {
        "assets": {},
        "composites": {},
        "measurements": {},
        "paths": {"state": tmp_path / "state.json", "wal": tmp_path / "wal.jsonl"},
        "secrets": {"influx": {"url": "x", "db": "y"}},
        "buckets": {"daily": "d", "intraday": "i"},
    }

    monkeypatch.setattr(main_mod, "load_config", lambda: Result.ok_payload(fake_config))
    make_influx_backend(monkeypatch)
    monkeypatch.setattr(main_mod, "State", FakeState)
    monkeypatch.setattr(main_mod, "FetchController", lambda assets, keys: FakeFetchController([]))
    make_composite_engine(monkeypatch, [("spread", {"value": 10}, 200)], fail="build")

    caplog.set_level("ERROR")

    with pytest.raises(SystemExit) as se:
        main_mod.main()

    assert se.value.code == 2
    assert "ERROR | Exiting due to error | error=simulated failure" in caplog.text
