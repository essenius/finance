# Copyright 2026 Rik Essenius
# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.
# File: src/finance/fetch/controller.py

from collections.abc import Callable, Iterable
from datetime import datetime

from ..common.applogger import AppLogger
from ..common.candle_identity import CandleIdentity
from ..common.guards import require
from ..common.model import FetchResult, Series, SeriesState
from ..common.series_calendar import SeriesCalendar
from ..common.time_utils import now_second_precision
from ..state.state import State

logger = AppLogger("fetch")


class FetchController:
    def __init__(self, *, now_provider: Callable[[], datetime] = now_second_precision):
        self.now = now_provider

    def fetch_incrementally(self, series_list: Iterable[Series], state: State) -> Iterable[FetchResult]:

        for series in series_list:
            series_id = series.require_id()
            state_entry = state.get_series_state(series_id)
            logger.debug(
                f"Fetching series: {series.name} ({series.id}). Stored range: {state_entry.first_point} - {state_entry.last_point}"
            )
            range = self._get_fetch_range(series=series, state=state_entry)
            if range is None:
                logger.debug("  Up to date")
                continue
            start, end, is_incremental = range
            logger.debug(
                f"  Range: {start} - {end} Publish range: {start.publish_label()} - {end.publish_label()} {'/I' if is_incremental else ''}"
            )
            yield series.asset.provider.fetch(series, start=start, end=end, is_incremental=is_incremental)

    # ----------------
    # Private methods
    # ----------------

    def _get_fetch_range(
        self, series: Series, state: SeriesState
    ) -> tuple[CandleIdentity, CandleIdentity, bool] | None:
        """
        Unified fetch decision: if fetch needed → return (start, end, is_incremental), else None
        """

        now = self.now()
        calendar = series.calendar
        first_req, last_req = self._get_required_range(series, now)

        # edge case. e.g. when retention horizon lands in a weekend
        if first_req > last_req:
            return None

        sweep_config = series.asset.provider.sweep_config(series.interval_delta())

        # if we have missing history, grab that first
        # This can mean we skip a daily publication (but that will be picked up next run)
        # we won't do the sweep now either
        prepend_range = self._get_prepend_range(calendar, state, first_req)
        if prepend_range is not None:
            start, end = prepend_range
            if end is None:
                # Full history update, is also a sweep
                state.update_sweep_state(sweep_config, last_req)
                end = last_req
            logger.debug(f"  Prepend range: {start} - {end}. Next sweep: {state.next_sweep}")
            return (start, end, False)

        # if we get here, state.last_point is set: only None the first time, when we do a full history
        start_point = calendar.from_store_label(require(state.last_point, "state.last_point") + series.interval_delta())
        sweep_start = state.get_sweep_start(sweep_config, last_req)
        if sweep_start is not None:
            sweep_start = calendar.from_store_label(sweep_start)
            start_point = min(start_point, sweep_start)
            logger.debug(f"  Sweep start: {start_point}. Next sweep: {state.next_sweep}")
            state.update_sweep_state(sweep_config, last_req)

        retention = series.retention_delta()
        if retention is not None:
            start_point = max(start_point, now - retention)
        if last_req.value < start_point:
            return None
        first_identity = calendar.snap_forward_identity(start_point)
        logger.debug(f"  Incremental range: {first_identity} - {last_req}")
        return (first_identity, last_req, True)

    @staticmethod
    def _get_prepend_range(
        calendar: SeriesCalendar, state: SeriesState, first_req: CandleIdentity
    ) -> tuple[CandleIdentity, CandleIdentity | None] | None:
        if state.first_point is None:
            return first_req, None  # full history

        last_missing = calendar.last_identity_before(state.first_point)
        if last_missing >= first_req:
            return first_req, last_missing
        return None

    @staticmethod
    def _get_required_range(series: Series, now: datetime) -> tuple[CandleIdentity, CandleIdentity]:
        calendar = series.calendar
        horizon = series.bootstrap_history_delta()
        retention_delta = series.retention_delta()
        if retention_delta is not None:
            horizon = min(horizon, retention_delta)

        oldest_required = now - horizon
        first_trade_time = calendar.first_trade_time()
        if first_trade_time is not None:
            oldest_required = max(first_trade_time, oldest_required)
        logger.debug(f"  Oldest required: {oldest_required}")

        first_identity = calendar.snap_forward_identity(oldest_required)

        # the last one we need is the last one that could have been published
        snap_identity = calendar.snap_back_identity(now)
        last_identity = calendar.snap_back_on_publish_time(now, snap_identity)

        logger.debug(f"  required range: {first_identity} - {last_identity}")
        return first_identity, last_identity
