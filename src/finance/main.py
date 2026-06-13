# Copyright 2026 Rik Essenius
# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.
# File: src/finance/main.py

from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import finance
from finance.common.model import Result
from finance.common.paths import get_project_root
from finance.fetch.provider import MarketDataProvider
from finance.state.storage import StateStorage

from .common.applogger import AppLogger
from .composites.engine import CompositeEngine
from .config.loader import ConfigLoader
from .fetch.controller import FetchController, create_providers
from .main_utils import process_result, unwrap
from .state.state import State
from .state.wal import JsonlWAL
from .timeseries import InfluxBackend

logger = AppLogger()


def main():
    return run()


def run(
    load_config: Callable[[], Result[dict[str, Any]]] = None,
    influx_backend_factory: Callable[
        [dict[str, Any], dict[str, Any]], Result[InfluxBackend]
    ] = InfluxBackend.from_config,
    state_factory: Callable[..., State] = State,
    state_storage_factory: Callable[[str], StateStorage] = StateStorage,
    fetch_controller_factory: Callable[[dict[str, Any], dict[str, Any]], FetchController] = FetchController,
    composite_engine_builder: Callable[[dict[str, Any], State], Result[CompositeEngine]] = CompositeEngine.build,
    wal_factory: Callable[[Path], JsonlWAL] = JsonlWAL,
    now: Callable[[], datetime] = None,
    provider_factory: Callable[[dict[str, Any], dict[str, Any]], dict[str, MarketDataProvider]] = create_providers,
) -> None:
    try:
        # these two have arguments, so shouldn't be used in defaults
        load_config = load_config or ConfigLoader(get_project_root()).load
        now = now or datetime.now(UTC)

        now_str = now().astimezone().isoformat(timespec="seconds")
        logger.info(f"Finance version: {finance.__version__} started at {now_str}")

        config = unwrap(load_config())

        paths = config["paths"]
        assets = config["assets"]
        composites = config["composites"]
        secrets = config["secrets"]
        buckets = config["buckets"]
        provider_cfg = config["providers"]

        def bucket_for(measurement: str) -> str:
            return config["measurements"][measurement]["bucket"]

        influx_result = influx_backend_factory(config["influx"], secrets["influx"])
        if not influx_result.ok:
            logger.error(reason=influx_result.reason, error=influx_result.error)
            raise SystemExit(1)
        wal = wal_factory(paths.get("wal"))
        storage = state_storage_factory(paths.get("state"))
        state = state_factory(series_store=influx_result.payload, wal=wal, storage=storage, bucket_for=bucket_for)

        fetch_failures = 0

        # Fetch and save primary asset metrics

        providers = provider_factory(api_keys=secrets.get("api_keys"), providers_config=provider_cfg)
        fetch_controller = fetch_controller_factory(assets, providers)
        for result in fetch_controller.fetch_incrementally(state):
            cfg = assets[result.measurement]
            if not process_result(result, state, cfg.get("tags"), cfg["bucket"]):
                fetch_failures += 1

        if fetch_failures:
            logger.error(f"Fetch completed with {fetch_failures} failures")

        # calculate and save composites
        engine = unwrap(composite_engine_builder(composites, state))

        composite_failures = 0

        for result in engine.evaluate_incrementally():
            cfg = composites[result.measurement]
            bucket = buckets[cfg["timeseries"]]
            if not process_result(result, state, cfg.get("tags"), bucket):
                composite_failures += 1

        if composite_failures:
            logger.error(f"Composite evaluation completed with {composite_failures} failures")

        # Persist state
        state.save()

        if fetch_failures or composite_failures:
            raise SystemExit(1)
        logger.info("Done.")
        return

    # catch the unwrap errors
    except Exception as e:
        logger.error("Exiting due to error", error=e)
        raise SystemExit(2) from None
