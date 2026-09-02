# Copyright 2026 Rik Essenius
# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.
# File: src/finance/fetch/controller.py

from collections.abc import Callable, Iterable
from datetime import datetime

from finance.common.guards import require

from ..common.applogger import AppLogger
from ..common.candle_identity import CandleIdentity
from ..common.configuration import ProviderConfig
from ..common.model import FetchResult, Series, SeriesState
from ..common.series_calendar import SeriesCalendar
from ..common.string_enums import SupportedProviders
from ..common.time_utils import now_second_precision
from ..common.types import Failure
from ..fetch.provider import MarketDataProvider
from ..state.state import State
from .ecb import EcbProvider
from .fred import FredProvider
from .yahoo import YahooProvider

PROVIDER_REGISTRY: dict[
    SupportedProviders,
    type[MarketDataProvider],
] = {
    SupportedProviders.YAHOO: YahooProvider,
    SupportedProviders.FRED: FredProvider,
    SupportedProviders.ECB: EcbProvider,
}

logger = AppLogger("fetch")


def create_providers(providers_config: dict[str, ProviderConfig]) -> dict[str, MarketDataProvider]:
    result = {
        name.value: provider_class(provider_config=providers_config[name.value])
        for name, provider_class in PROVIDER_REGISTRY.items()
    }
    return result


class FetchController:
    def __init__(
        self,
        get_provider: Callable[[str], MarketDataProvider | None],
        **kwargs,
    ):
        self.get_provider = get_provider
        self.now = kwargs.pop("now_provider", now_second_precision)

    def fetch_incrementally(self, series_list: Iterable[Series], state: State) -> Iterable[FetchResult]:

        for series in series_list:
            series_id = series.require_id()
            state_entry = state.get_series_state(series_id)
            asset = series.asset
            provider = self.get_provider(asset.provider)
            if not provider:
                yield Failure(reason=f"no provider '{asset.provider}'", error=f"Skipped series '{series.name}'")
                continue
            range = self._get_fetch_range(series=series, provider=provider, state=state_entry)
            if range is None:
                continue
            start, end, is_incremental = range
            logger.debug(
                f"series: {series.name} ({series.id}) Store range: {start.store_label()} - {end.store_label()} Publish range: {start.publish_label()} - {end.publish_label()} {'/I' if is_incremental else ''}"
            )
            yield provider.fetch(series, asset, start, end, is_incremental)

    # ----------------
    # Private methods
    # ----------------

    def _get_fetch_range(
        self, series: Series, provider: MarketDataProvider, state: SeriesState
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

        sweep_config = provider.provider_config.get_sweep(series.interval_delta())

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
            return (start, end, False)

        sweep_start = state.get_sweep_start(sweep_config, last_req)
        if sweep_start is not None:
            retention = series.retention_delta()
            if retention is not None:
                sweep_start = max(sweep_start, now - retention)
            first_identity = calendar.snap_forward_identity(sweep_start)
            state.update_sweep_state(sweep_config, last_req)
            return (first_identity, last_req, False)

        last_point = require(state.last_point, "state.last_point")
        if last_req.store_label() > last_point:
            first_identity = calendar.snap_forward_identity(last_point + series.interval_delta())
            return (first_identity, last_req, True)
        return None

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
            logger.debug(f"oldest required: {oldest_required}")

        first_identity = calendar.snap_forward_identity(oldest_required)

        # the last one we need is the last one that could have been published
        snap_identity = calendar.snap_back_identity(now)
        last_identity = calendar.snap_back_on_publish_time(now, snap_identity)

        logger.debug(
            f"series: {series.name} ({series.id}): {first_identity.store_label()} - {last_identity.store_label()}"
        )
        return first_identity, last_identity
