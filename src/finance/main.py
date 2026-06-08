# Copyright 2026 Rik Essenius
# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.
# File: src/finance/main.py

from datetime import datetime

import finance

from .common.applogger import AppLogger
from .composites.engine import CompositeEngine
from .config.loader import load_config
from .fetch.controller import FetchController
from .main_utils import process_result, unwrap
from .state.manager import State
from .state.wal import JsonlWAL
from .timeseries import InfluxBackend

logger = AppLogger()

def main():
    print("CALLSITE:", State, id(State))

    try:
        now = datetime.now().astimezone().isoformat(timespec="seconds")
        logger.info(f"Finance version: {finance.__version__} started at {now}")

        config = unwrap(load_config())

        paths = config["paths"]
        assets = config["assets"]
        composites = config["composites"]
        secrets = config["secrets"]
        buckets = config["buckets"]

        def bucket_for(measurement: str) -> str:
            return config["measurements"][measurement]["bucket"]

        timeseries_client = InfluxBackend.from_secrets(secrets["influx"])
        wal = JsonlWAL(paths.get("wal"))
        state = State(timeseries_client=timeseries_client, wal=wal, path=paths.get("state"), bucket_for=bucket_for)

        fetch_failures = 0

        # Fetch and save primary asset metrics
        fetch_controller = FetchController(assets, secrets.get("api_keys"))
        for result in fetch_controller.fetch_incrementally(state):
            cfg = assets[result.measurement]
            if not process_result(result, state, cfg.get("tags"), cfg["bucket"]):
                fetch_failures += 1

        if fetch_failures:
            logger.error(f"Fetch completed with {fetch_failures} failures")

        # calculate and save composites
        engine = unwrap(CompositeEngine.build(composites, state))

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

