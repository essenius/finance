# Copyright 2026 Rik Essenius
# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.
# File: src/finance/main.py

from datetime import datetime

import finance

from .common.log_mixin import LogMixin
from .composites import evaluate_composites
from .config.loader import load_config
from .fetch.controller import FetchController
from .state.manager import State
from .state.wal import JsonlWAL
from .timeseries import TimeSeriesClient
from .write import write_metric


class AppLogger(LogMixin):
    pass


logger = AppLogger()


def main():
    now = datetime.now().astimezone().isoformat(timespec="seconds")
    logger.info(f"Finance version: {finance.__version__} started at {now}")

    config = load_config()
    paths = config["paths"]
    assets = config["assets"]
    composites = config["composites"]
    secrets = config["secrets"]
    buckets = config["buckets"]

    timeseries_client = TimeSeriesClient(secrets["influx"])
    wal = JsonlWAL(paths.get("wal"))
    state = State(timeseries_client, wal, paths.get("state"))

    # Fetch primary asset metrics
    fetch_controller = FetchController(assets, secrets["api_keys"])
    fetched = fetch_controller.fetch_all(state)

    failures = 0

    for asset_name, (fields, timestamp) in fetched.items():
        asset_cfg = assets[asset_name]
        series_type = asset_cfg["timeseries"]
        bucket = buckets[series_type]
        measurement = asset_name

        result = write_metric(bucket, measurement, fields, timestamp, state)
        if not result["ok"]:
            failures += 1

    # Evaluate composites
    computed = evaluate_composites(composites, state)

    for name, (fields, timestamp) in computed.items():
        composite_cfg = composites[name]
        series_type = composite_cfg["timeseries"]
        bucket = buckets[series_type]
        measurement = name

        result = write_metric(bucket, measurement, fields, timestamp, state)
        if not result["ok"]:
            failures += 1

    # Persist state
    state.save()

    if failures:
        logger.error(f"Completed with {failures} write failures")
        raise SystemExit(1)
    logger.info("Done.")
