# Copyright 2026 Rik Essenius
# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.
# File: src/finance/orchestrator.py

from dataclasses import asdict
from typing import Literal, overload

import finance

from .common.applogger import AppLogger
from .common.model import FetchResult, Series, SeriesPoints
from .common.result import Result
from .fetch.controller import FetchController
from .registry.registry import Registry
from .state.state import State
from .timeseries.series_backend import SeriesBackend

logger = AppLogger()


@overload
def unwrap[T](result: Result[T], throw: Literal[True] = True) -> T: ...


@overload
def unwrap[T](result: Result[T], throw: Literal[False]) -> T | None: ...


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


class Orchestrator:
    config: dict
    backend: SeriesBackend
    registry: Registry
    state: State

    def __init__(self, backend: SeriesBackend, registry: Registry, state: State, fetcher: FetchController):
        self.backend = backend
        self.registry = registry
        self.state = state
        self.fetcher = fetcher

    def prepare(self):
        logger.info(f"Finance version: {finance.__version__} started.")

        logger.debug("Loading state")
        flush_count = unwrap(self.state.load(), throw=False)
        logger.debug(f"Flushed {flush_count} items from the WAL")

        logger.debug("Reconciling loaded config with backend")
        saved_assets = unwrap(self.backend.get_assets())
        to_persist = self.registry.merge_and_find_new_assets(saved_assets)
        for asset in to_persist:
            logger.debug(f"Persisting asset {asset.name}")
            stored = unwrap(self.backend.store_asset(asset))
            self.registry.register_stored_asset(stored)

        saved_series = unwrap(self.backend.get_series())
        reconciled_series = self.registry.reconcile_series(saved_series)
        for series in reconciled_series.to_persist:
            logger.debug(f"Persisting series {series.name}")
            stored = unwrap(self.backend.store_series(series))
            self.registry.register_stored_series(stored)

        self.backend.refresh_short_lived_series_ids()

    def ingest_points(self, points: SeriesPoints, series: Series):
        # this assumes the payload is ordered on increasing time
        batch_first = points[0].time
        batch_last = points[-1].time
        # correct if it was the other way around
        if batch_first > batch_last:
            batch_first, batch_last = batch_last, batch_first

        logger.debug(
            f"Retrieved range for {series.name}: {batch_first.isoformat()} - {batch_last.isoformat()}, {len(points)} records."
        )

        all_ok = True

        for point in points:
            ingest_result = self.state.ingest(point)
            # log any errors
            unwrap(ingest_result, throw=False)
            if not ingest_result.ok:
                all_ok = False

        if all_ok:
            self.state.update_state(series.id, batch_first, batch_last)
            range = self.state.series[series.id]
            logger.debug(
                f"Range for {series.name} after updating: {range.first_point.isoformat()} - {range.last_point.isoformat()}"
            )
        return all_ok

    def handle_fetch_response(self, result: FetchResult):
        payload = unwrap(result, throw=False)

        if not result.ok:
            return False

        series = self.registry.get_series_by_name(result.series_name)

        if payload.metadata is not None:
            asset_to_save = self.registry.register_provider_metadata(series.asset_id, payload.metadata)
            if asset_to_save is not None:
                stored = unwrap(self.backend.store_asset(asset_to_save))
                self.registry.register_stored_asset(stored)

        if not payload.points:
            return True

        return self.ingest_points(payload.points, series)

    def finalize(self, fetch_failures: int) -> int:

        if fetch_failures:
            logger.error(f"Fetch completed with {fetch_failures} failures")

        # CO:# calculate and save composites -- removed from V1 scope. TODO: re-introduce
        # CO: engine = unwrap(composite_engine_builder(composites, state))

        # CO: composite_failures = 0

        # CO: for result in engine.evaluate_incrementally():
        # CO:    cfg = composites[result.series_name]
        # CO:    #bucket = buckets[cfg["timeseries"]]
        # CO:    if not process_result(result, state, cfg.get("tags")):
        # CO:        composite_failures += 1

        # CO: if composite_failures:
        # CO:    logger.error(f"Composite evaluation completed with {composite_failures} failures")

        # Persist state
        self.state.save()

        if fetch_failures:  # or composite_failures:
            return 1
        logger.info("Done.")
        return 0

    def run(self) -> int:
        self.prepare()

        fetch_failures = 0

        for result in self.fetcher.fetch_incrementally(self.state):
            if not self.handle_fetch_response(result):
                fetch_failures += 1

        return self.finalize(fetch_failures)
