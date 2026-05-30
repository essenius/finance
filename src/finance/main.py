# Copyright 2026 Rik Essenius
# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.
# File: src/finance/main.py

from datetime import datetime

import finance

from .common.log_mixin import LogMixin
from .composites import evaluate_composites
from .config.loader import load_config
from .fetch.controller import FetchController
from .state.manager import load_state, save_state
from .write import write_metric
from .write.influx import InfluxWriter


class AppLogger(LogMixin):
    pass


logger = AppLogger()


def main():
    now = datetime.now().astimezone().isoformat(timespec="seconds")
    logger.info(f"Finance version: {finance.__version__} started at {now}")

    config = load_config()

    assets = config["assets"]
    composites = config["composites"]
    secrets = config["secrets"]
    buckets = config["buckets"]

    state = load_state()
    influx_writer = InfluxWriter(secrets["influx"])

    # ---------------------------------------------------------
    # 1. Fetch primary asset metrics
    # ---------------------------------------------------------
    fetch_controller = FetchController(assets, secrets["api_keys"])
    fetched = fetch_controller.fetch_all(state)

    for asset_name, (fields, ts) in fetched.items():
        asset_cfg = assets[asset_name]
        series_type = asset_cfg["timeseries"]
        bucket = buckets[series_type]
        measurement = asset_name

        write_metric(bucket, measurement, fields, ts, state, influx_writer)

    # ---------------------------------------------------------
    # 2. Evaluate composites
    # ---------------------------------------------------------
    computed = evaluate_composites(composites, state)

    for name, (fields, ts) in computed.items():
        composite_cfg = composites[name]
        series_type = composite_cfg["timeseries"]
        bucket = buckets[series_type]
        measurement = name

        write_metric(bucket, measurement, fields, ts, state, influx_writer)

    # ---------------------------------------------------------
    # 3. Persist state
    # ---------------------------------------------------------
    save_state(state)
    logger.info("Done.")
