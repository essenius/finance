# Copyright 2026 Rik Essenius
# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.
# File: src/finance/main.py

from collections.abc import Callable, Iterable
from datetime import datetime
from pathlib import Path
from typing import Any

import finance
from finance.timeseries.backend_protocol import BackendProtocol

from .common.applogger import AppLogger, LogConfig
from .common.dict_utils import deep_merge
from .common.model import BACKEND, Asset, ProviderConfig, Series
from .common.result import Result
from .common.time_utils import now_second_precision

# from .composites.engine import CompositeEngine
from .config.loader import ConfigLoader
from .fetch.controller import FetchController, create_providers
from .fetch.provider import MarketDataProvider
from .main_utils import parse_args, process_result, reconcile_registry, unwrap
from .registry.registry import Registry
from .state.state import State
from .state.wal import JsonlWAL
from .timeseries.series_backend import SeriesBackend
from .timeseries.timescale_sql import TimescaleSqlClient

logger = AppLogger()


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    return run(args.config)


def run(
    config_path: Path | None = None,
    load_config: Callable[[], Result[dict[str, Any]]] = None,
    registry_factory: Callable[..., Registry] = Registry,
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
    reconcile: Callable[[Registry, SeriesBackend], None] = reconcile_registry,
    now: Callable[[], datetime] = None,
) -> None:
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
        log_section = {} if not config_result.ok else config_result.payload.get("logging")
        log_config.setup(log_section)
        # Now we have a valid json logger, and we can start logging.
        logger.info(f"Finance version: {finance.__version__} started.")
        config = unwrap(config_result)

        paths = config["paths"]
        asset_list = config["assets"]
        series_list = config["series"]
        # CO: composites = config["composites"]
        secrets = config["secrets"]
        provider_cfg = config["providers"]

        registry = registry_factory()
        registry.load_yaml_assets(asset_list)
        registry.load_yaml_series(series_list)

        backend_result = backend_factory(deep_merge(secrets[BACKEND], config[BACKEND]), sql_factory)
        if not backend_result.ok:
            logger.error(reason=backend_result.reason, error=backend_result.error)
            return 1

        backend: SeriesBackend = backend_result.payload

        logger.debug("Reconciling loaded config with backend")
        reconcile(registry, backend)

        logger.debug("Loading state")
        wal = wal_factory(paths.get("wal"))
        state = state_factory(backend=backend_result.payload, wal=wal)
        # load the state and load/flush the wal
        flush_count = unwrap(state.load(), throw=False)
        logger.debug(f"Flushed {flush_count} items from the WAL")

        fetch_failures = 0

        # Fetch and save primary asset metrics

        providers = provider_factory(api_keys=secrets.get("api_keys"), providers_config=provider_cfg)
        fetch_controller = fetch_controller_factory(registry.all_series(), registry.get_asset_by_id, providers.get)
        for result in fetch_controller.fetch_incrementally(state):
            logger.debug(f"Fetched {result.series_name}")
            series = registry.get_series_by_name(result.series_name)
            if not process_result(result, state, series):
                fetch_failures += 1

        if fetch_failures:
            logger.error(f"Fetch completed with {fetch_failures} failures")

        # CO:# calculate and save composites -- removed from V1 scope. TODO: re-introduce
        # CO: engine = unwrap(composite_engine_builder(composites, state))

        # CO: composite_failures = 0

        # CO: for result in engine.evaluate_incrementally():
        # CO:    cfg = composites[result.series_name]
        # CO:    #bucket = buckets[cfg["timeseries"]]
        # CO:    if not process_result(result, state, cfg.get("tags")):
        # CO:        composite_failures += 1

        # CO: if composite_failures:
        # CO:    logger.error(f"Composite evaluation completed with {composite_failures} failures")

        # Persist state
        state.save()

        if fetch_failures:  # or composite_failures:
            return 1
        logger.info("Done.")
        return 0

    # catch the unwrap errors
    except Exception:
        logger.exception("Exiting due to error")
        return 2
