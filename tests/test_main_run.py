# Copyright 2026 Rik Essenius
# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.
# File: tests/test_main_run.py

# File: tests/test_run.py

from collections.abc import Iterable
from unittest.mock import MagicMock, Mock

import pytest

from finance.common.model import DailyValuePoint, FetchResult, Result, Series, SeriesPoint, SeriesResult, SeriesState
from finance.main import run
from finance.state.state import State

# ---------------------------------------------------------------------------
# Helper classes/functions for fetch + composite engines
# ---------------------------------------------------------------------------


def registry_factory():
    result = MagicMock()
    result.get_asset_by_id = MagicMock()
    result.get_asset_by_name = MagicMock()
    return result


class FakeFetchController:
    def __init__(self, outputs):
        self.outputs = outputs

    def fetch_incrementally(self, state) -> Iterable[FetchResult]:
        for id, value, ts in self.outputs:
            fp = DailyValuePoint(series_id=id, timestamp=ts, value=value)
            yield FetchResult.ok_payload("spx", [fp])


"""
TODO re-introduce in V2
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
"""

# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_run_happy_path(tmp_path, caplog, fixed_now, state_deps, make_asset, make_series):

    timescale_backend, wal, storage = state_deps

    state_holder = {}
    caplog.set_level("DEBUG")
    asset = make_asset()
    fake_config = {
        "paths": {"wal": tmp_path / "wal.jsonl", "state": tmp_path / "state.json"},
        "secrets": {"timescaledb": {"url": "x", "db": "y"}, "api_keys": {"yahoo": "YKEY"}},
        "assets": {"spx": asset},
        "series": {"spx_daily": make_series(asset)},
        # "composites": {"spread": {"tags": {"c": "s"}, RESOLUTION: DAILY}},
        # "measurements": {"spread": {"bucket": DAILY}},
        # "buckets": {"intraday": "finance_intraday", "daily": "finance_daily"},
        "providers": {},
        "timescaledb": {},
    }

    def state_factory(series_store, wal, storage):
        state = State(series_store, wal, storage)
        state._rebuild_measurement_state = lambda *_: None
        state_holder["state"] = state
        return state

    def load_config():
        return Result.ok_payload(fake_config)

    def fetch_controller_factory(series, get_assets, get_providers):
        return FakeFetchController([(1, 4321, 100)])

    # def composite_engine_builder(composites, state):
    #    return Result.ok_payload(FakeCompositeEngine([("spread", {"value": 10}, 200)]))

    run(
        load_config=load_config,
        registry_factory=registry_factory,
        backend_factory=lambda *_: Result.ok_payload(timescale_backend),
        state_factory=state_factory,
        state_storage_factory=lambda *_: storage,
        fetch_controller_factory=fetch_controller_factory,
        #   composite_engine_builder=composite_engine_builder,
        wal_factory=lambda *_: wal,
        reconcile=lambda *_: None,
        now=fixed_now,
        provider_factory=lambda api_keys, providers_config: {},
    )

    state = state_holder["state"]

    # Validate state writes
    assert state.series.get(1) == SeriesState(first_timestamp=100, last_timestamp=100)

    assert "Finance version:" in caplog.text
    assert "Done." in caplog.text


def test_run_fetch_failure(tmp_path, caplog, fixed_now, make_asset, make_series):
    caplog.set_level("ERROR")

    asset = make_asset()
    fake_config = {
        "paths": {"wal": tmp_path / "wal.jsonl", "state": tmp_path / "state.json"},
        "secrets": {"timescaledb": {"url": "x", "db": "y"}, "api_keys": {}},
        "assets": {"boom": asset},
        "series": {"boom_daily": make_series(asset)},
        # "composites": {},
        "providers": {},
        "timescaledb": {},
    }

    def load_config():
        return Result.ok_payload(fake_config)

    def backend_factory(*_):
        return Result.ok_payload(Mock())

    def wal_factory(path):
        return Mock()

    class FailingState:
        def __init__(self, *_, **kwargs):
            self.calls = []
            self.saved = False

        def ingest(self, series: Series, point: SeriesPoint):
            return SeriesResult.fail(point.series_id, "Boom", "simulated failure")

        def save(self):
            self.saved = True

    def fetch_controller_factory(series, get_assets, get_providers):
        return FakeFetchController([(1, 1, 100)])

    # def composite_engine_builder(composites, state):
    #    return Result.ok_payload(FakeCompositeEngine([]))

    with pytest.raises(SystemExit) as se:
        run(
            load_config=load_config,
            registry_factory=registry_factory,
            backend_factory=backend_factory,
            state_factory=FailingState,
            state_storage_factory=lambda *_: Mock(),
            fetch_controller_factory=fetch_controller_factory,
            #   composite_engine_builder=composite_engine_builder,
            wal_factory=wal_factory,
            reconcile=lambda *_: None,
            now=fixed_now,
            provider_factory=lambda api_keys, providers_config: {},
        )

    assert se.value.code == 1
    assert "reason=Boom" in caplog.text
    assert "Fetch completed with 1 failures" in caplog.text


"""
TODO: re-enable in V2
def test_run_composite_failure(tmp_path, caplog, fixed_now, state):
    fake_config = {
        "assets": {},
        "composites": {"spread": {"tags": {}, RESOLUTION: DAILY}},
        "measurements": {"spread": {"bucket": DAILY}},
        "paths": {"state": tmp_path / "state.json", "wal": tmp_path / "wal.jsonl"},
        "secrets": {"timescaledb": {"url": "x", "db": "y"}, "api_keys": {}},
        #"buckets": {"daily": "d", "intraday": "i"},
        "providers": {},
        "timescaledb": {},
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
"""


def test_run_crash(caplog):
    def load_config():
        raise ValueError("Boom!")

    with pytest.raises(SystemExit) as se:
        run(load_config=load_config)

    assert se.value.code == 2
    assert "Exiting due to error" in caplog.text
    assert "Boom!" in caplog.text


def test_run_backend_failure(tmp_path, caplog, fixed_now):
    fake_config = {
        "paths": {"wal": tmp_path / "wal.jsonl", "state": tmp_path / "state.json"},
        "assets": {},
        "series": {},
        "composites": {},
        "measurements": {},
        "secrets": {"timescaledb": {}, "api_keys": {}},
        "providers": {},
        "timescaledb": {},
    }

    def load_config():
        return Result.ok_payload(fake_config)

    def backend_factory(*_):
        return Result.fail("Backend initialization failed", RuntimeError("boom"))

    def fetch_controller_factory(*_):
        return FakeFetchController([])

    # def composite_engine_builder(*_):
    #    return Result.ok_payload(FakeCompositeEngine([]))

    caplog.set_level("ERROR")

    with pytest.raises(SystemExit) as se:
        run(
            load_config=load_config,
            backend_factory=backend_factory,
            state_factory=Mock,
            fetch_controller_factory=fetch_controller_factory,
            # composite_engine_builder=composite_engine_builder,
            wal_factory=Mock,
            now=fixed_now,
            provider_factory=lambda api_keys, providers_config: {},
        )

    assert se.value.code == 1
    assert "Backend initialization failed" in caplog.text
    assert "boom" in caplog.text
