# Copyright 2026 Rik Essenius
# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.
# File: src/finance/orchestrator.py

from typing import Literal, overload

import finance
from finance.common.types import AppError

from .common.applogger import AppLogger
from .common.guards import require
from .common.model import FetchResult, Series, SeriesPoints
from .common.types import Result
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
    Unwrap a Result[T], logging warnings and optionally raising on failure
    """
    result_dict = result.to_log_dict()

    if result.ok is False:
        logger.error(**result_dict)
        if throw:
            if result.error:
                raise AppError(f"{result.reason}: {result.error}")
            raise AppError(result.reason)
        return_value = None
    else:
        return_value = result.payload

    # we can have warnings with ok, they still have results
    if result.warnings:
        logger.warning(**result_dict)
    return return_value


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

    def run(self) -> int:
        self._prepare()

        fetch_failures = 0

        for result in self.fetcher.fetch_incrementally(self.state):
            if not self._handle_fetch_response(result):
                fetch_failures += 1

        return self._finalize(fetch_failures)

    # ----------------
    # Private methods
    # ----------------

    def _finalize(self, fetch_failures: int) -> int:

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

    def _handle_fetch_response(self, result: FetchResult) -> bool:
        payload = unwrap(result, throw=False)

        if result.ok is False:
            return False

        payload = require(payload)
        series = self.registry.get_series_by_id(payload.series_id)

        if payload.metadata is not None:
            asset_to_save = self.registry.register_provider_metadata(
                require(series.asset_id, "asset ID"), payload.metadata
            )
            if asset_to_save is not None:
                stored = unwrap(self.backend.store_asset(asset_to_save))
                self.registry.register_stored_asset(stored)

        if not payload.points:
            return True

        return self._ingest_points(payload.points, series)

    def _ingest_points(self, points: SeriesPoints, series: Series):
        # this assumes the payload is ordered low-high or high-low
        batch_first = points[0].time
        batch_last = points[-1].time
        # correct first and last if it was high-low
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
            if ingest_result.ok is False:
                all_ok = False

        if all_ok:
            series_id = require(series.id)
            self.state.update_state(series_id, batch_first, batch_last)
            range = self.state.series[series_id]
            logger.debug(
                f"Range for {series.name} after updating: {require(range.first_point).isoformat()} - {require(range.last_point).isoformat()}"
            )
        return all_ok

    def _prepare(self):
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
