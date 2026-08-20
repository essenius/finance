# Copyright 2026 Rik Essenius
# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.
# File: tests/test_main_run.py

from collections.abc import Iterable
from unittest.mock import MagicMock, Mock

from finance.common.model import FetchData, FetchResult, SeriesPoint
from finance.common.result import Result
from finance.main import run

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
        for id, value, time in self.outputs:
            fp = SeriesPoint(series_id=id, time=time, close=value)
            yield FetchResult.ok_payload(FetchData(series_id=id, points=[fp], metadata=None))


def make_config():
    return {
        "paths": {"wal": "wal.jsonl"},
        "logging": {"json": True, "level": "info"},
        "secrets": {"timescaledb": {}, "api_keys": {}},
        "assets": {},
        "series": {},
        "providers": {},
        "timescaledb": {},
    }


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
# New Tests
# ---------------------------------------------------------------------------


def test_run_wires_dependencies_and_returns_orchestrator_result():
    config = make_config()

    registry = Mock()
    backend = Mock()
    wal = Mock()
    state = Mock()
    providers = Mock()
    fetcher = Mock()

    orchestrator = Mock()
    orchestrator.run.return_value = 17

    def load_config():
        return Result.ok_payload(config)

    def registry_factory(assets, series):
        assert assets is config["assets"]
        assert series is config["series"]
        return registry

    def backend_factory(*_):
        return Result.ok_payload(backend)

    def state_factory(*, backend, wal):
        assert backend is backend
        assert wal is wal
        return state

    def provider_factory(*, api_keys, providers_config):
        assert api_keys is config["secrets"]["api_keys"]
        assert providers_config is config["providers"]
        return providers

    def fetch_controller_factory(series, get_asset, get_provider):
        assert series is registry.all_series()
        assert get_asset is registry.get_asset_by_id
        assert get_provider is providers.get
        return fetcher

    def orchestrator_factory(*, backend, registry, state, fetcher):
        assert backend is backend
        assert registry is registry
        assert state is state
        assert fetcher is fetcher
        return orchestrator

    assert (
        run(
            load_config=load_config,
            registry_factory=registry_factory,
            backend_factory=backend_factory,
            state_factory=state_factory,
            provider_factory=provider_factory,
            fetch_controller_factory=fetch_controller_factory,
            orchestrator_factory=orchestrator_factory,
            wal_factory=lambda _: wal,
        )
        == 17
    )

    orchestrator.run.assert_called_once_with()


def test_run_returns_one_when_backend_initialization_fails():

    backend_factory = Mock(return_value=Result.fail("Backend initialization failed", "boom"))
    orchestrator_factory = Mock()

    result = run(
        load_config=lambda: Result.ok_payload(make_config()),
        backend_factory=backend_factory,
        orchestrator_factory=orchestrator_factory,
    )

    assert result == 1
    orchestrator_factory.assert_not_called()


def test_run_returns_two_when_unexpected_exception_occurs(clean_logging, caplog):
    def load_config():
        raise RuntimeError("Boom!")

    result = run(load_config=load_config)

    assert result == 2
    assert any(m.startswith("ERROR | Exiting due to error | exception.message=Boom!") for m in caplog.messages)


# ---------------------------------------------------------------------------
# Old Tests
# ---------------------------------------------------------------------------

'''
def test_run_happy_path(tmp_path, json_caplog, fixed_now, state_deps, make_asset, make_series):

    backend, wal = state_deps
    backend.flush.return_value = Result(0)
    backend.get_series_states.return_value = Result.ok_payload({})
    now = fixed_now()
    state_holder = {}
    json_caplog.set_level("DEBUG")
    asset = make_asset()
    fake_config = {
        "paths": {"wal": tmp_path / "wal.jsonl", "state": tmp_path / "state.json"},
        "logging": {"json": True, "level": "info"},
        "secrets": {"timescaledb": {"url": "x", "db": "y"}, "api_keys": {"yahoo": "YKEY"}},
        "assets": {"spx": asset},
        "series": {"spx_daily": make_series(asset)},
        # CO: "composites": {"spread": {"tags": {"c": "s"}, RESOLUTION: DAILY}},
        # CO: "measurements": {"spread": {"bucket": DAILY}},
        # CO: "buckets": {"intraday": "finance_intraday", "daily": "finance_daily"},
        "providers": {},
        "timescaledb": {},
    }

    def state_factory(backend, wal):
        state = State(backend, wal)
        state_holder["state"] = state
        return state

    def load_config():
        return Result.ok_payload(fake_config)

    def fetch_controller_factory(series, get_assets, get_providers):
        return FakeFetchController([(1, 4321, now)])

    # CO: def composite_engine_builder(composites, state):
    # CO:    return Result.ok_payload(FakeCompositeEngine([("spread", {"value": 10}, 200)]))

    # note that sql_factory was not mocked so it takes the original.

    run(
        load_config=load_config,
        registry_factory=registry_factory,
        backend_factory=lambda *_: Result.ok_payload(backend),
        state_factory=state_factory,
        fetch_controller_factory=fetch_controller_factory,
        #   composite_engine_builder=composite_engine_builder,
        wal_factory=lambda *_: wal,
        reconcile=lambda *_: None,
        now=fixed_now,
        provider_factory=lambda api_keys, providers_config: {},
    )

    state = state_holder["state"]

    # Validate state writes
    series_state = state.series.get(1)
    assert series_state.first_point, series_state.last_point == (now, now)

    assert '"message": "Finance version: ' in json_caplog.text
    assert '"message": "Done."' in json_caplog.text


def test_run_fetch_failure(tmp_path, json_caplog, fixed_now, make_asset, make_series):
    json_caplog.set_level("ERROR")
    json_caplog.handler.setFormatter(JsonFormatter())

    asset = make_asset()
    fake_config = {
        "paths": {"wal": tmp_path / "wal.jsonl"},
        "logging": {"json": True, "level": "info"},
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

        def ingest(self, point: SeriesPoint):
            return SeriesResult.fail(point.series_id, "Boom", "simulated failure")

        def save(self):
            self.saved = True

        def load(self):
            return Result.ok_payload(0)

    def fetch_controller_factory(series, get_assets, get_providers):
        return FakeFetchController([(1, 1, fixed_now())])

    # CO: def composite_engine_builder(composites, state):
    # CO:    return Result.ok_payload(FakeCompositeEngine([]))

    exit_value = run(
        load_config=load_config,
        registry_factory=registry_factory,
        backend_factory=backend_factory,
        state_factory=FailingState,
        fetch_controller_factory=fetch_controller_factory,
        #   composite_engine_builder=composite_engine_builder,
        wal_factory=wal_factory,
        reconcile=lambda *_: None,
        now=fixed_now,
        provider_factory=lambda api_keys, providers_config: {},
    )

    assert exit_value == 1

    assert '"reason": "Boom", "error": "simulated failure"' in json_caplog.text
    assert '"message": "Fetch completed with 1 failures"' in json_caplog.text


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


def test_run_crash(clean_logging, caplog):
    def load_config():
        raise ValueError("Boom!")

    result = run(load_config=load_config)

    assert result == 2
    assert any(m.startswith("ERROR | Exiting due to error | exception.message=Boom!") for m in caplog.messages)


def test_run_backend_failure(tmp_path, json_caplog, fixed_now):
    fake_config = {
        "paths": {"wal": tmp_path / "wal.jsonl", "state": tmp_path / "state.json"},
        "logging": {"json": True, "level": "info"},
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

    # CO: def composite_engine_builder(*_):
    # CO:    return Result.ok_payload(FakeCompositeEngine([]))

    json_caplog.set_level("ERROR")

    result = run(
        load_config=load_config,
        backend_factory=backend_factory,
        state_factory=Mock,
        fetch_controller_factory=fetch_controller_factory,
        # CO: composite_engine_builder=composite_engine_builder,
        wal_factory=Mock,
        now=fixed_now,
        provider_factory=lambda api_keys, providers_config: {},
    )

    assert result == 1
    assert "Backend initialization failed" in json_caplog.text
    assert "boom" in json_caplog.text
'''
