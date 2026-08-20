# Copyright 2026 Rik Essenius
# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.
# File: src/finance/main_utils.py

'''TODO: delete
import argparse
from dataclasses import asdict
from pathlib import Path

from .common.applogger import AppLogger
from .common.model import FetchResult, Series
from .common.result import Result
from .registry.registry import Registry
from .state.state import State
from .timeseries.series_backend import SeriesBackend

logger = AppLogger()


def parse_args(argv: list[str] | None = None):
    parser = argparse.ArgumentParser(description="Finance ingestion service")
    parser.add_argument("--config", type=Path, help="Path to the YAML configuration file (absolute or relative)")
    return parser.parse_args(argv)


def unwrap[T](result: Result[T], throw: bool = True) -> T | None:
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


def reconcile_registry(registry: Registry, backend: SeriesBackend):
    saved_assets = unwrap(backend.get_assets())

    to_persist = registry.merge_and_find_new_assets(saved_assets)
    for asset in to_persist:
        stored = unwrap(backend.store_asset(asset))
        registry.register_stored_asset(stored)

    # CO: registry.load_db_assets(saved_assets)

    # CO: reconciled_assets = registry.reconcile_assets()
    # CO: for asset in reconciled_assets.to_persist:
    # CO:     stored = unwrap(backend.store_asset(asset))
    # CO:     registry.register_stored_asset(stored)

    # series must be done after asset since it refers to final assets
    saved_series = unwrap(backend.get_series())
    registry.load_db_series(saved_series)

    reconciled_series = registry.reconcile_series()
    for series in reconciled_series.to_persist:
        stored = unwrap(backend.store_series(series))
        registry.register_stored_series(stored)

    backend.refresh_short_lived_series_ids()


def process_result(
    result: FetchResult, state: State, series: Series, registry: Registry, backend: SeriesBackend
) -> bool:
    """
    Process a FetchResult:
    - unwrap the MeasurementResult
    - handle metadata if returned
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

    if payload.metadata is not None:
        asset_to_save = registry.register_provider_metadata(series.asset_id, payload.metadata)
        if asset_to_save is not None:
            stored = unwrap(backend.store_series(series))
            registry.register_stored_series(stored)

    if not payload.points:
        return True

    all_ok = True

    points = payload.points

    # this assumes the payload is ordered on increasing time
    batch_first = points[0].time
    batch_last = points[-1].time
    # correct if it was the other way around
    if batch_first > batch_last:
        batch_first, batch_last = batch_last, batch_first

    logger.debug(
        f"Retrieved range for {series.name}: {batch_first.isoformat()} - {batch_last.isoformat()}, {len(points)} records."
    )

    for point in points:
        ingest_result = state.ingest(point)
        # log any errors
        unwrap(ingest_result, throw=False)
        if not ingest_result.ok:
            all_ok = False

    if all_ok:
        state.update_state(point.series_id, batch_first, batch_last)
        range = state.series[point.series_id]
        logger.debug(
            f"Range for {series.name} after updating: {range.first_point.isoformat()} - {range.last_point.isoformat()}"
        )
    return all_ok
'''
