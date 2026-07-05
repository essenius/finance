# Copyright 2026 Rik Essenius
# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.
# File: src/finance/main.py

from collections.abc import Callable, Iterable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import finance
from finance.common.model import BACKEND, Asset, ProviderConfig, Result, Series
from finance.fetch.provider import MarketDataProvider
from finance.registry.registry import Registry
from finance.state.storage import StateStorage
from finance.timeseries.timescale_backend import TimescaleBackend

from .common.applogger import AppLogger

# from .composites.engine import CompositeEngine
from .config.loader import ConfigLoader
from .fetch.controller import FetchController, create_providers
from .main_utils import parse_args, process_result, reconcile_registry, unwrap
from .state.state import State
from .state.wal import JsonlWAL

logger = AppLogger()


def main(argv: list[str] | None = None):
    args = parse_args(argv)
    return run(args.config)


def run(
    config_path: Path | None = None,
    load_config: Callable[[], Result[dict[str, Any]]] = None,
    registry_factory: Callable[..., Registry] = Registry,
    backend_factory: Callable[
        [dict[str, Any], Callable[[int], Series]], Result[TimescaleBackend]
    ] = TimescaleBackend.from_config,
    provider_factory: Callable[[dict[str, Any], dict[str, Any]], dict[str, MarketDataProvider]] = create_providers,
    state_factory: Callable[..., State] = State,
    state_storage_factory: Callable[[str], StateStorage] = StateStorage,
    fetch_controller_factory: Callable[
        [Iterable[Series], Callable[[int], Asset], Callable[[str], ProviderConfig]], FetchController
    ] = FetchController,
    # composite_engine_builder: Callable[[dict[str, Any], State], Result[CompositeEngine]] = CompositeEngine.build,
    wal_factory: Callable[[Path], JsonlWAL] = JsonlWAL,
    reconcile: Callable[[Registry, TimescaleBackend], None] = reconcile_registry,
    now: Callable[[], datetime] = None,
) -> None:
    try:
        # these two have arguments, so shouldn't be used in defaults
        load_config = load_config or ConfigLoader(cwd=Path.cwd(), config_path=config_path).load
        now = now or (lambda: datetime.now(UTC))
        now_str = now().astimezone().isoformat(timespec="seconds")
        logger.info(f"Finance version: {finance.__version__} started at {now_str}")

        config = unwrap(load_config())

        paths = config["paths"]
        asset_list = config["assets"]
        series_list = config["series"]
        # composites = config["composites"]
        secrets = config["secrets"]
        provider_cfg = config["providers"]

        registry = registry_factory()
        registry.load_yaml_assets(asset_list)
        registry.load_yaml_series(series_list)

        backend_result = backend_factory(secrets[BACKEND] | config[BACKEND], registry.get_series_by_id)
        if not backend_result.ok:
            logger.error(reason=backend_result.reason, error=backend_result.error)
            raise SystemExit(1)

        backend: TimescaleBackend = backend_result.payload

        reconcile(registry, backend)

        wal = wal_factory(paths.get("wal"))
        storage = state_storage_factory(paths.get("state"))
        state = state_factory(backend=backend_result.payload, wal=wal, storage=storage)
        # load the state and load/flush the wal
        flush_count = unwrap(state.load(), throw=False)
        logger.debug(f"Flushed {flush_count} items from the WAL")

        fetch_failures = 0

        # Fetch and save primary asset metrics

        providers = provider_factory(api_keys=secrets.get("api_keys"), providers_config=provider_cfg)
        fetch_controller = fetch_controller_factory(registry.all_series(), registry.get_asset_by_id, providers.get)
        for result in fetch_controller.fetch_incrementally(state):
            series = registry.get_series_by_name(result.series_name)
            if not process_result(result, state, series):
                fetch_failures += 1

        if fetch_failures:
            logger.error(f"Fetch completed with {fetch_failures} failures")

        ## calculate and save composites -- removed from V1 scope. TODO: re-introduce
        # engine = unwrap(composite_engine_builder(composites, state))

        # composite_failures = 0

        # for result in engine.evaluate_incrementally():
        #    cfg = composites[result.series_name]
        #    #bucket = buckets[cfg["timeseries"]]
        #    if not process_result(result, state, cfg.get("tags")):
        #        composite_failures += 1

        # if composite_failures:
        #    logger.error(f"Composite evaluation completed with {composite_failures} failures")

        # Persist state
        state.save()

        if fetch_failures:  # or composite_failures:
            raise SystemExit(1)
        logger.info("Done.")
        return

    # catch the unwrap errors
    except Exception as e:
        logger.error("Exiting due to error", error=e)
        raise SystemExit(2) from None
