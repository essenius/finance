# Copyright 2026 Rik Essenius
# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.
# File: tests/test_main_run.py

from collections.abc import Callable, Iterator
from pathlib import Path
from unittest.mock import Mock

from pytest import LogCaptureFixture

from finance.common.configuration import LogConfig, TimescaleConfig
from finance.common.model import ProviderProtocol
from finance.common.types import AppError, Failure, Result, Success
from finance.config.loader import AppConfig
from finance.fetch.controller import FetchController
from finance.main import run
from finance.orchestrator import Orchestrator
from finance.registry.registry import Registry
from finance.state.state import State
from finance.state.wal import JsonlWAL
from finance.timeseries.series_backend import SeriesBackend

# ---------------------------------------------------------------------------
# Helper classes/functions for fetch + composite engines
# ---------------------------------------------------------------------------


def make_config() -> AppConfig:
    return AppConfig(
        paths={"wal": Path("wal.jsonl")},
        logging=LogConfig.from_config({}),
        assets=[],
        series=[],
        providers=Mock(spec=dict[str, ProviderProtocol]),
        timescaledb=TimescaleConfig.from_config({"host": "h", "db": "d", "user": "u", "password": "p"}),
    )


"""
TODO re-introduce in V2
class FakeCompositeEngine:
    def __init__(self, outputs=None, fail_eval=False):
        self.outputs = outputs or []
        self.fail_eval = fail_eval

    def evaluate_incrementally(self):
        if self.fail_eval:
            for measurement, _, _ in self.outputs:
                yield MeasurementFailure(reason=measurement, "simulated failure")
        else:
            for measurement, fields, ts in self.outputs:
                fp = FetchPoint(fields=fields, timestamp=ts)
                yield MeasurementSuccess(measurement, [fp])
"""

# ---------------------------------------------------------------------------
# New Tests
# ---------------------------------------------------------------------------


def test_run_wires_dependencies_and_returns_orchestrator_result():
    config = make_config()

    registry = Mock(spec=Registry)
    backend = Mock(spec=SeriesBackend)
    wal = Mock(spec=JsonlWAL)
    state = Mock(spec=State)
    fetcher = Mock(spec=FetchController)

    orchestrator = Mock(spec=Orchestrator)
    orchestrator.run.return_value = 17

    def load_config() -> Result[AppConfig]:
        return Success(config)

    def registry_factory(assets, series) -> Registry:
        assert assets is config.assets
        assert series is config.series
        return registry

    def backend_factory(*_) -> Result[SeriesBackend]:
        return Success(backend)

    def state_factory(*, backend, wal) -> State:
        assert backend is backend
        assert wal is wal
        return state

    def fetch_controller_factory() -> FetchController:
        return fetcher

    def orchestrator_factory(*, backend, registry, state, fetcher) -> Orchestrator:
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
            fetch_controller_factory=fetch_controller_factory,
            orchestrator_factory=orchestrator_factory,
            wal_factory=lambda _: wal,
        )
        == 17
    )

    orchestrator.run.assert_called_once_with()


def test_run_returns_one_when_backend_initialization_fails():

    backend_factory = Mock(return_value=Failure(reason="Backend initialization failed", error="boom"))
    orchestrator_factory = Mock(spec=Callable[..., Orchestrator])

    result = run(
        load_config=lambda: Success(make_config()),
        backend_factory=backend_factory,
        orchestrator_factory=orchestrator_factory,
    )

    assert result == 1
    orchestrator_factory.assert_not_called()


def test_run_returns_two_when_unexpected_exception_occurs(clean_logging: Iterator[None], caplog: LogCaptureFixture):
    def load_config():
        raise AppError("Boom!")

    result = run(load_config=load_config)

    assert result == 2
    assert any(m.startswith("ERROR | Exiting due to error | exception.message=Boom!") for m in caplog.messages)
