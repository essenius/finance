# Copyright 2026 Rik Essenius
# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.
# File: ops/test_connectivity.py

from pathlib import Path
from unittest.mock import Mock

from finance.common.model import SeriesPoint
from finance.common.time_utils import now_second_precision
from finance.config.loader import ConfigLoader
from finance.orchestrator import Orchestrator, unwrap
from finance.registry.registry import Registry
from finance.timeseries import SeriesBackend


def print_list(input_list: list, caption: str) -> None:
    print(caption)
    for entry in input_list:
        print(f"{entry}")


def main():
    project_root = Path(__file__).resolve().parent

    print("Loading config...")
    loader = ConfigLoader(cwd=project_root, config_path=Path("config.yaml"))
    cfg_result = loader.load()
    if cfg_result.ok is False:
        print("Config load failed:", cfg_result.reason, cfg_result.error)
        return

    app_cfg = cfg_result.payload
    asset_list = app_cfg.assets
    series_list = app_cfg.series
    print_list(asset_list, "loaded assets")
    print_list(series_list, "loaded series: ")

    if len(series_list) == 0:
        print("Terminating as there are no series")
        return

    env_cfg = app_cfg.timescaledb
    print(f"environment config: {env_cfg}")
    print("creating backend")

    registry = Registry(assets=asset_list, series=series_list)

    backend_result = SeriesBackend.from_config(env_cfg)
    if backend_result.ok is False:
        print("Backend creation failed:", backend_result.reason, backend_result.error)
        return

    backend = backend_result.payload

    orchestrator = Orchestrator(backend=backend, registry=registry, state=Mock(), fetcher=Mock())
    print("Preparing...")
    orchestrator.prepare()

    print_list(list(registry.all_assets()), "registry assets")
    print_list(list(registry.all_series()), "registry series")

    assets = unwrap(backend.get_assets())
    print_list(assets, "backend get_assets()")

    series = unwrap(backend.get_series())
    print_list(series, "backend get_series()")

    now = now_second_precision()
    print(f"writing point at {now}")
    id = list(registry.all_series())[0].id
    assert id is not None
    point = SeriesPoint(id, now, close=123.48)
    result = backend.add_point(point)
    if result.ok is False:
        print(f"Write failed: {result.reason}, {result.error}")
        return

    print("Write OK")
    # Read it back (TODO not right yet. Fix)

    print("Reading back...")
    read_result = backend.read_last(id)

    if read_result.ok is False:
        print("Read failed:", read_result.error)
        return

    print("Read OK")
    print(f"Returned point: {read_result.payload}")


if __name__ == "__main__":
    main()
