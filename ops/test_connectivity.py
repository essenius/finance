# Copyright 2026 Rik Essenius
# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.
# File: ops/test_connectivity.py

from pathlib import Path

from finance.common.dict_utils import deep_merge
from finance.common.model import SeriesPoint
from finance.common.time_utils import now_second_precision
from finance.config.loader import ConfigLoader
from finance.main_utils import reconcile_registry, unwrap
from finance.registry.registry import Registry
from finance.timeseries import SeriesBackend


def print_list(input_list: list, caption: str) -> None:
    print(caption)
    for entry in input_list:
        print(f"{entry}")


def main():
    project_root = Path(__file__).resolve().parent

    print("Loading config...")
    loader = ConfigLoader(cwd=project_root, config_path="config.yaml")
    cfg_result = loader.load()
    if not cfg_result.ok:
        print("Config load failed:", cfg_result.reason, cfg_result.error)
        return

    full_cfg = cfg_result.payload
    asset_list = full_cfg["assets"]
    series_list = full_cfg["series"]
    print_list(asset_list, "loaded assets")
    print_list(series_list, "loaded series: ")

    if len(series_list) == 0:
        print("Terminating as there are no series")
        return

    secrets = full_cfg["secrets"]["timescaledb"]
    env_cfg = full_cfg["timescaledb"]
    print(f"secrets: {secrets}")
    print(f"environment config: {env_cfg}")
    print("creating backend")

    registry = Registry()
    registry.load_yaml_assets(asset_list)
    registry.load_yaml_series(series_list)

    backend_result = SeriesBackend.from_config(
        config=deep_merge(secrets, env_cfg),  # series_by_id=registry.get_series_by_id
    )
    if not backend_result.ok:
        print("Backend creation failed:", backend_result.reason, backend_result.error)
        return

    backend = backend_result.payload

    print("reconciling registry")
    reconcile_registry(registry, backend)

    print_list(registry.all_assets(), "registry assets")
    print_list(registry.all_series(), "registry series")

    assets = unwrap(backend.get_assets())
    print_list(assets, "backend get_assets()")

    series = unwrap(backend.get_series())
    print_list(series, "backend get_series()")

    now = now_second_precision()
    print(f"writing point at {now}")
    id = registry.all_series()[0].id
    point = SeriesPoint(id, now, close=123.48)
    result = backend.add_point(point)
    if not result.ok:
        print(f"Write failed: {result.reason}, {result.error}")
        return

    print("Write OK")
    # Read it back

    print("Reading back...")
    read_result = backend.read_last(id)

    if not read_result.ok:
        print("Read failed:", read_result.error)
        return

    print("Read OK")
    print(f"Returned point: {read_result.payload}")


if __name__ == "__main__":
    main()
