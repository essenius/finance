# Copyright 2026 Rik Essenius
# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.
# File: ops/test_connectivity.py

from datetime import UTC, datetime
from pathlib import Path

from finance.common.model import SeriesPoint
from finance.config.loader import ConfigLoader
from finance.main_utils import reconcile_registry, unwrap
from finance.registry.registry import Registry
from finance.timeseries import TimescaleBackend


def main():
    project_root = Path(__file__).resolve().parent

    print("Loading config...")
    loader = ConfigLoader(project_root)
    cfg_result = loader.load()
    if not cfg_result.ok:
        print("Config load failed:", cfg_result.reason, cfg_result.error)
        return

    full_cfg = cfg_result.payload
    asset_list = full_cfg["assets"]
    series_list = full_cfg["series"]
    print("loaded assets: ")
    for entry in asset_list:
        print(f"{entry}")
    print("loaded series: ")
    for entry in series_list:
        print(f"{entry}")

    if len(series_list) == 0:
        print("Terminating as there are no series")
        return

    secrets = full_cfg["secrets"]["timescaledb"]
    env_cfg = full_cfg["timescaledb"]
    print(f"secrets: {secrets}")
    print(f"environment config: {env_cfg}")
    print("creating backend")

    backend_result = TimescaleBackend.from_config(secrets | env_cfg)
    if not backend_result.ok:
        print("Backend creation failed:", backend_result.reason, backend_result.error)
        return

    backend = backend_result.payload

    print("reconciling registry")
    registry = Registry()
    registry.load_yaml_assets(asset_list)
    registry.load_yaml_series(series_list)
    reconcile_registry(registry, backend)

    print("registry assets")
    for entry in registry.all_assets():
        print(entry)

    print("registry series")
    for entry in registry.all_series():
        print(entry)

    print("backend get_assets():")
    assets = unwrap(backend.get_assets())
    for entry in assets:
        print(entry)

    print("backend get_series():")
    series = unwrap(backend.get_series())
    for entry in series:
        print(entry)

    now = datetime.now(tz=UTC)
    print(f"writing point at {now}")
    id = registry.all_series()[0].id
    point = SeriesPoint(id, now, close=123.48)
    result = backend.add(point)
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
