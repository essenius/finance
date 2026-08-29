# Copyright 2026 Rik Essenius
# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.
# File: src/finance/main.py

import argparse
from collections.abc import Callable, Iterable
from datetime import datetime
from pathlib import Path

from finance.common.configuration import ProviderConfig, TimescaleConfig

from .common.applogger import AppLogger, LogConfigurator
from .common.model import Asset, Series
from .common.time_utils import now_second_precision
from .common.types import Result

# from .composites.engine import CompositeEngine
from .config.loader import AppConfig, ConfigLoader
from .fetch.controller import FetchController, create_providers
from .fetch.provider import MarketDataProvider
from .orchestrator import Orchestrator, unwrap
from .registry.registry import Registry
from .state.state import State
from .state.wal import JsonlWAL
from .timeseries.backend_protocol import BackendProtocol
from .timeseries.series_backend import SeriesBackend
from .timeseries.timescale_sql import TimescaleSqlClient

logger = AppLogger()


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    return run(args.config)


def parse_args(argv: list[str] | None = None):
    parser = argparse.ArgumentParser(description="Finance ingestion service")
    parser.add_argument("--config", type=Path, help="Path to the YAML configuration file (absolute or relative)")
    return parser.parse_args(argv)


def run(
    config_path: Path | None = None,
    load_config: Callable[[], Result[AppConfig]] | None = None,
    registry_factory: Callable[[Iterable[Asset], Iterable[Series]], Registry] = Registry,
    sql_factory: Callable[..., BackendProtocol] = TimescaleSqlClient,
    backend_factory: Callable[
        [TimescaleConfig, Callable[..., BackendProtocol]], Result[SeriesBackend]
    ] = SeriesBackend.from_config,
    provider_factory: Callable[[dict[str, ProviderConfig]], dict[str, MarketDataProvider]] = create_providers,
    state_factory: Callable[..., State] = State,
    fetch_controller_factory: Callable[
        [Iterable[Series], Callable[[int], Asset | None], Callable[[str], MarketDataProvider | None]], FetchController
    ] = FetchController,
    # composite_engine_builder: Callable[[dict[str, Any], State], Result[CompositeEngine]] = CompositeEngine.build,
    wal_factory: Callable[[Path], JsonlWAL] = JsonlWAL,
    orchestrator_factory: Callable[..., Orchestrator] = Orchestrator,
    now: Callable[[], datetime] | None = None,
) -> int:
    try:
        # these two have arguments, so shouldn't be used in defaults
        load_config = load_config or ConfigLoader(cwd=Path.cwd(), config_path=config_path).load
        now = now or now_second_precision

        log_configurator = LogConfigurator()
        # bootstrap logger is a minimal text logger, so if an exception happens
        # before the json logger is configured, we can still log it.
        log_configurator.bootstrap()
        # Config loader can have errors, but is also needed to setup logging.
        # So if the config loader fails, we take default logging settings.
        config: AppConfig = unwrap(load_config())
        log_configurator.setup(config.logging)
        # Now we have a valid json logger.

        # CO: composites = config["composites"]

        registry = registry_factory(config.assets, config.series)

        backend_result = backend_factory(config.timescaledb, sql_factory)
        if backend_result.ok is False:
            logger.error(reason=backend_result.reason, error=backend_result.error)
            return 1

        backend: SeriesBackend = backend_result.payload

        wal = wal_factory(config.paths["wal"])
        state = state_factory(backend=backend, wal=wal)
        providers = provider_factory(config.providers)
        fetch_controller = fetch_controller_factory(registry.all_series(), registry.get_asset_by_id, providers.get)

        orchestrator = orchestrator_factory(backend=backend, registry=registry, state=state, fetcher=fetch_controller)
        return orchestrator.run()

    # catch the unwrap errors
    except Exception:
        logger.exception("Exiting due to error")
        return 2
