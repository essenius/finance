# Copyright 2026 Rik Essenius
# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.
# File: ops/test_connectivity.py

from pathlib import Path
from unittest.mock import Mock

from finance.common.applogger import AppLogger, LogConfigurator
from finance.common.types import Failure
from finance.config.loader import ConfigLoader
from finance.orchestrator import Orchestrator
from finance.registry.registry import Registry
from finance.state.state import State
from finance.state.wal import JsonlWAL
from finance.timeseries import SeriesBackend


def print_list(input_list: list, caption: str) -> None:
    logger.info(f"{caption}:")
    for entry in input_list:
        logger.info(f"  {entry}")


def print_error(msg: str, fail: Failure) -> None:
    logger.error(msg, **fail.to_log_dict())


logger = AppLogger()


def main():
    project_root = Path(__file__).resolve().parent

    log_configurator = LogConfigurator()
    log_configurator.bootstrap()

    logger.info("Loading config...")
    loader = ConfigLoader(cwd=project_root, config_path=Path("config.yaml"))
    cfg_result = loader.load()
    if cfg_result.ok is False:
        print_error("Config load failed", cfg_result)
        return

    app_cfg = cfg_result.payload
    asset_list = app_cfg.assets
    series_list = app_cfg.series
    print_list(asset_list, "loaded assets")
    print_list(series_list, "loaded series")

    if len(series_list) == 0:
        logger.warning("Terminating as there are no series")
        return

    env_cfg = app_cfg.timescaledb
    logger.info(f"environment config: {env_cfg}")
    logger.info("creating backend")

    registry = Registry(assets=asset_list, series=series_list)

    backend_result = SeriesBackend.from_config(env_cfg, app_cfg.providers.get)
    if backend_result.ok is False:
        print_error("Backend creation failed", backend_result)
        return

    backend = backend_result.payload
    wal = JsonlWAL(app_cfg.paths["wal"])

    state = State(backend=backend, wal=wal)
    orchestrator = Orchestrator(backend=backend, registry=registry, state=state, fetcher=Mock())
    logger.info("Preparing...")
    orchestrator._prepare()

    print_list(list(registry.all_assets()), "registry assets")
    print_list(list(registry.all_series()), "registry series")

    id = list(registry.all_series())[0].id
    assert id is not None

    state_result = backend.get_series_states()
    if state_result.ok is False:
        print_error("Read states failed", state_result)
        return
    if len(state_result.payload) <= 0:
        logger.warning("No data returned")
        return
    id, value = next(iter(state_result.payload.items()))
    logger.info("Read OK")
    logger.info(
        f"first series state: series ID {id}, first point: {value.first_point}, last point: {value.last_point}, next sweep: {value.next_sweep}"
    )


if __name__ == "__main__":
    main()
