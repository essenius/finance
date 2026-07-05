# Copyright 2026 Rik Essenius
# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.
# File: src/finance/main_utils.py

import argparse
from dataclasses import asdict
from pathlib import Path
from typing import TypeVar

from finance.common.applogger import AppLogger
from finance.common.model import FetchResult, Result, Series
from finance.registry.registry import Registry
from finance.state.state import State
from finance.timeseries.timescale_backend import TimescaleBackend

logger = AppLogger()

T = TypeVar("T")


def parse_args(argv: list[str] | None = None):
    parser = argparse.ArgumentParser(description="Finance ingestion service")
    parser.add_argument("--config", type=Path, help="Path to the YAML configuration file (absolute or relative)")
    return parser.parse_args(argv)


def unwrap(result: Result[T], throw: bool | None = True) -> T | None:
    """
    Unwrap a Result[T]:
    - log warnings
    - return payload on success
    - optionally throw ValueError on failure
    """
    result_dict = asdict(result)
    result_dict.pop("payload")
    if not result.ok:
        logger.error(**result_dict)
        if throw:
            raise (ValueError(f"{result.reason}: {result.error}")) if result.error else ValueError(result.reason)

    # we can have warnings with ok, they still have results
    if result.warnings:
        logger.warning(**result_dict)
    return result.payload


def reconcile_registry(registry: Registry, backend: TimescaleBackend):
    saved_assets = unwrap(backend.get_assets())
    registry.load_db_assets(saved_assets)

    reconciled_assets = registry.reconcile_assets()
    for asset in reconciled_assets.to_persist:
        stored = unwrap(backend.store_asset(asset))
        registry.register_final_asset(stored)

    # series must be done after asset since it refers to final assets
    saved_series = unwrap(backend.get_series())
    registry.load_db_series(saved_series)

    reconciled_series = registry.reconcile_series()
    for series in reconciled_series.to_persist:
        stored = unwrap(backend.store_series(series))
        registry.register_final_series(stored)

    backend.refresh_short_lived_series_ids()


def process_result(result: FetchResult, state: State, series: Series) -> bool:
    """
    Process a FetchResult:
    - unwrap the MeasurementResult
    - iterate over all FetchPoints
    - build a ResultPoint for each
    - ingest each one
    - only update state timestamps if all ingests succeeded
    - return True only if all ingests succeed (skip counts as success)

    """
    payload = unwrap(result, throw=False)

    # if the raw Result failed, stop here
    if not result.ok:
        return False

    if not payload:
        return True  # nothing to do

    all_ok = True

    batch_first = payload[0].time
    batch_last = payload[-1].time

    for point in payload:
        ingest_result = state.ingest(series, point)
        # log any errors
        unwrap(ingest_result, throw=False)
        if not ingest_result.ok:
            all_ok = False

    if all_ok:
        state.update_range(point.series_id, batch_first, batch_last)
    return all_ok
