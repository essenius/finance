# Copyright 2026 Rik Essenius
# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.
# File: tests/test_main_run.py

# File: tests/test_run.py

from unittest.mock import Mock

import pytest

from finance.common.model import FetchPoint, MeasurementResult, Result
from finance.main import run
from finance.state.state import State
from finance.state.storage import StateStorage

# ---------------------------------------------------------------------------
# Helper classes for fetch + composite engines
# ---------------------------------------------------------------------------


class FakeFetchController:
    def __init__(self, outputs):
        self.outputs = outputs

    def fetch_incrementally(self, state):
        for measurement, fields, ts in self.outputs:
            fp = FetchPoint(fields=fields, timestamp=ts)
            yield MeasurementResult.ok_payload(measurement, [fp])


class FakeCompositeEngine:
    def __init__(self, outputs=None, fail_eval=False):
        self.outputs = outputs or []
        self.fail_eval = fail_eval

    def evaluate_incrementally(self):
        if self.fail_eval:
            for measurement, _, _ in self.outputs:
                yield MeasurementResult.fail(measurement, "simulated failure")
        else:
            for measurement, fields, ts in self.outputs:
                fp = FetchPoint(fields=fields, timestamp=ts)
                yield MeasurementResult.ok_payload(measurement, [fp])


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_run_happy_path(tmp_path, caplog, fixed_now, state_deps):

    influx, wal, storage = state_deps

    state_holder = {}
    caplog.set_level("DEBUG")
    fake_config = {
        "paths": {"wal": tmp_path / "wal.jsonl", "state": tmp_path / "state.json"},
        "secrets": {"influx": {"url": "x", "db": "y"}, "api_keys": {"yahoo": "YKEY"}},
        "assets": {"spx": {"tags": {"m": "s"}, "timeseries": "intraday", "bucket": "finance_intraday"}},
        "composites": {"spread": {"tags": {"c": "s"}, "timeseries": "daily"}},
        "measurements": {"spread": {"bucket": "daily"}},
        "buckets": {"intraday": "finance_intraday", "daily": "finance_daily"},
        "providers": {},
        "influx": {},
    }

    def state_factory(series_store, wal, storage, bucket_for):
        state = State(series_store, wal, storage, bucket_for)
        state._rebuild_measurement_state = lambda *_: None
        state_holder["state"] = state
        return state

    def load_config():
        return Result.ok_payload(fake_config)

    def fetch_controller_factory(assets, providers):
        return FakeFetchController([("spx", {"price": 4321}, 100)])

    def composite_engine_builder(composites, state):
        return Result.ok_payload(FakeCompositeEngine([("spread", {"value": 10}, 200)]))

    run(
        load_config=load_config,
        influx_backend_factory=lambda *_: Result.ok_payload(influx),
        state_factory=state_factory,
        state_storage_factory=lambda *_: storage,
        fetch_controller_factory=fetch_controller_factory,
        composite_engine_builder=composite_engine_builder,
        wal_factory=lambda *_: wal,
        now=fixed_now,
        provider_factory=lambda api_keys, providers_config: {},
    )

    # check if we have a good _bucket_for()

    state = state_holder["state"]
    result = state._bucket_for("spread")
    assert result == "daily"

    # Validate state writes
    assert state._state.get("spx") == {"fields": {"price": 4321}, "last_timestamp": 100, "first_timestamp": 100}
    assert state._state.get("spread") == {"fields": {"value": 10}, "last_timestamp": 200, "first_timestamp": 200}

    assert "Finance version:" in caplog.text
    assert "Done." in caplog.text


def test_run_fetch_failure(tmp_path, caplog, fixed_now):
    caplog.set_level("ERROR")

    fake_config = {
        "paths": {"wal": tmp_path / "wal.jsonl", "state": tmp_path / "state.json"},
        "secrets": {"influx": {"url": "x", "db": "y"}, "api_keys": {}},
        "assets": {"boom": {"tags": {}, "timeseries": "daily", "bucket": "finance_daily"}},
        "composites": {},
        "measurements": {},
        "buckets": {"daily": "finance_daily"},
        "providers": {},
        "influx": {},
    }

    def load_config():
        return Result.ok_payload(fake_config)

    def influx_backend_factory(*_):
        return Result.ok_payload(Mock())

    def wal_factory(path):
        return Mock()

    class FailingState:
        def __init__(self, *_, **kwargs):
            self.calls = []
            self.saved = False
            self.bucket_for = kwargs["bucket_for"]

        def ingest(self, write):
            return Result.fail(write.measurement, "simulated failure")

        def save(self):
            self.saved = True

    def fetch_controller_factory(assets, providers):
        return FakeFetchController([("boom", {"value": 1}, 100)])

    def composite_engine_builder(composites, state):
        return Result.ok_payload(FakeCompositeEngine([]))

    with pytest.raises(SystemExit) as se:
        run(
            load_config=load_config,
            influx_backend_factory=influx_backend_factory,
            state_factory=FailingState,
            fetch_controller_factory=fetch_controller_factory,
            composite_engine_builder=composite_engine_builder,
            wal_factory=wal_factory,
            now=fixed_now,
            provider_factory=lambda api_keys, providers_config: {},
        )

    assert se.value.code == 1
    assert "reason=boom" in caplog.text
    assert "Fetch completed with 1 failures" in caplog.text


def test_run_composite_failure(tmp_path, caplog, fixed_now, state):
    fake_config = {
        "assets": {},
        "composites": {"spread": {"tags": {}, "timeseries": "daily"}},
        "measurements": {"spread": {"bucket": "daily"}},
        "paths": {"state": tmp_path / "state.json", "wal": tmp_path / "wal.jsonl"},
        "secrets": {"influx": {"url": "x", "db": "y"}, "api_keys": {}},
        "buckets": {"daily": "d", "intraday": "i"},
        "providers": {},
        "influx": {},
    }

    def load_config():
        return Result.ok_payload(fake_config)

    def influx_backend_factory(*_):
        return Result.ok_payload(Mock())

    def wal_factory(path):
        return Mock()

    def state_factory(*args, **kwargs):
        storage = StateStorage(kwargs["path"])
        state = State(kwargs["series_store"], kwargs["wal"], storage, kwargs["bucket_for"])
        state._rebuild_measurement_state = lambda *_: None
        return state

    def fetch_controller_factory(*_):
        return FakeFetchController([])

    def composite_engine_builder(composites, state):
        return Result.ok_payload(
            FakeCompositeEngine(
                outputs=[("spread", {"value": 10}, 200)],
                fail_eval=True,
            )
        )

    caplog.set_level("ERROR")

    with pytest.raises(SystemExit) as se:
        run(
            load_config=load_config,
            influx_backend_factory=influx_backend_factory,
            state_factory=lambda *_, **__: state,
            fetch_controller_factory=fetch_controller_factory,
            composite_engine_builder=composite_engine_builder,
            wal_factory=wal_factory,
            now=fixed_now,
            provider_factory=lambda api_keys, providers_config: {},
        )

    assert se.value.code == 1
    assert "reason=simulated failure" in caplog.text
    assert "Composite evaluation completed with 1 failures" in caplog.text


def test_run_unwrap_error(tmp_path, caplog, fixed_now, state):
    fake_config = {
        "assets": {},
        "composites": {},
        "measurements": {},
        "paths": {"state": tmp_path / "state.json", "wal": tmp_path / "wal.jsonl"},
        "secrets": {"influx": {"url": "x", "db": "y"}, "api_keys": {}},
        "buckets": {"daily": "d", "intraday": "i"},
        "providers": {},
        "influx": {},
    }

    def load_config():
        return Result.ok_payload(fake_config)

    def influx_backend_factory(*_):
        return Result.ok_payload(Mock())

    def wal_factory(path):
        return Mock()

    def fetch_controller_factory(*_):
        return FakeFetchController([])

    def composite_engine_builder(*_):
        return Result.fail("simulated failure")

    caplog.set_level("ERROR")

    with pytest.raises(SystemExit) as se:
        run(
            load_config=load_config,
            influx_backend_factory=influx_backend_factory,
            state_factory=lambda *_, **__: state,
            fetch_controller_factory=fetch_controller_factory,
            composite_engine_builder=composite_engine_builder,
            wal_factory=wal_factory,
            now=fixed_now,
            provider_factory=lambda api_keys, providers_config: {},
        )

    assert se.value.code == 2
    assert "Exiting due to error" in caplog.text
    assert "simulated failure" in caplog.text


def test_run_influx_backend_failure(tmp_path, caplog, fixed_now):
    fake_config = {
        "paths": {"wal": tmp_path / "wal.jsonl", "state": tmp_path / "state.json"},
        "assets": {},
        "composites": {},
        "measurements": {},
        "secrets": {"influx": {}, "api_keys": {}},
        "buckets": {},
        "providers": {},
        "influx": {},
    }

    def load_config():
        return Result.ok_payload(fake_config)

    def influx_backend_factory(*_):
        return Result.fail("Influx backend initialization failed", RuntimeError("boom"))

    def wal_factory(path):
        return Mock()

    def state_factory(*args, **kwargs):
        return Mock()

    def fetch_controller_factory(*_):
        return FakeFetchController([])

    def composite_engine_builder(*_):
        return Result.ok_payload(FakeCompositeEngine([]))

    caplog.set_level("ERROR")

    with pytest.raises(SystemExit) as se:
        run(
            load_config=load_config,
            influx_backend_factory=influx_backend_factory,
            state_factory=state_factory,
            fetch_controller_factory=fetch_controller_factory,
            composite_engine_builder=composite_engine_builder,
            wal_factory=wal_factory,
            now=fixed_now,
            provider_factory=lambda api_keys, providers_config: {},
        )

    assert se.value.code == 1
    assert "Influx backend initialization failed" in caplog.text
    assert "boom" in caplog.text
