# Copyright 2026 Rik Essenius
# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.
# File: src/finance/main.py

import argparse
from collections.abc import Callable, Iterable
from datetime import datetime
from pathlib import Path
from typing import Any

from .common.applogger import AppLogger, LogConfig
from .common.configuration import ProviderConfig
from .common.dict_utils import deep_merge
from .common.guards import require
from .common.model import BACKEND, Asset, Series
from .common.result import Result
from .common.time_utils import now_second_precision

# from .composites.engine import CompositeEngine
from .config.loader import ConfigLoader
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


def parse_args(argv: list[str] | None = None):
    parser = argparse.ArgumentParser(description="Finance ingestion service")
    parser.add_argument("--config", type=Path, help="Path to the YAML configuration file (absolute or relative)")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    return run(args.config)


def run(
    config_path: Path | None = None,
    load_config: Callable[[], Result[dict[str, Any]]] | None = None,
    registry_factory: Callable[[dict[str, Asset], dict[str, Series]], Registry] = Registry,
    sql_factory: Callable[..., BackendProtocol] = TimescaleSqlClient,
    backend_factory: Callable[
        [dict[str, Any], Callable[..., BackendProtocol]], Result[SeriesBackend]
    ] = SeriesBackend.from_config,
    provider_factory: Callable[[dict[str, Any], dict[str, Any]], dict[str, MarketDataProvider]] = create_providers,
    state_factory: Callable[..., State] = State,
    fetch_controller_factory: Callable[
        [Iterable[Series], Callable[[int], Asset], Callable[[str], ProviderConfig]], FetchController
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

        log_config = LogConfig()
        # bootstrap logger is a minimal text logger, so if an exception happens
        # before the json logger is configured, we can still log it.
        log_config.bootstrap()
        # Config loader can have errors, but is also needed to setup logging.
        # So if the config loader fails, we take default logging settings.
        config_result = load_config()
        log_section = (
            {}
            if config_result.ok is False
            else require(config_result.payload.get("logging"), "logging entry in config")
        )
        log_config.setup(log_section)
        # Now we have a valid json logger, and we can start logging.
        config = unwrap(config_result)

        # CO: composites = config["composites"]
        secrets = config["secrets"]

        registry = registry_factory(config["assets"], config["series"])

        backend_result = backend_factory(deep_merge(secrets[BACKEND], config[BACKEND]), sql_factory)
        if backend_result.ok is False:
            logger.error(reason=backend_result.reason, error=backend_result.error)
            return 1

        backend: SeriesBackend = backend_result.payload

        wal = wal_factory(config["paths"].get("wal"))
        state = state_factory(backend=backend, wal=wal)
        providers = provider_factory(api_keys=secrets.get("api_keys"), providers_config=config["providers"])
        fetch_controller = fetch_controller_factory(registry.all_series(), registry.get_asset_by_id, providers.get)

        orchestrator = orchestrator_factory(backend=backend, registry=registry, state=state, fetcher=fetch_controller)
        return orchestrator.run()

    # catch the unwrap errors
    except Exception:
        logger.exception("Exiting due to error")
        return 2
