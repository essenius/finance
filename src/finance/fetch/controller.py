# Copyright 2026 Rik Essenius
# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.
# File: src/finance/fetch/controller.py

from collections.abc import Callable, Iterable
from datetime import datetime, timedelta

from finance.common.series_calendar import SeriesCalendar
from finance.common.string_enums import SupportedProviders
from finance.common.time_utils import now_second_precision
from finance.fetch.provider import MarketDataProvider

from ..common.model import Asset, FetchResult, ProviderConfig, Series, SeriesState, SweepConfig
from ..state.state import State
from .ecb import EcbProvider
from .fred import FredProvider
from .yahoo import YahooProvider

# make sure this aligns with PROVIDERS in config/loader.py
PROVIDER_REGISTRY = {
    SupportedProviders.YAHOO: YahooProvider,
    SupportedProviders.FRED: FredProvider,
    SupportedProviders.ECB: EcbProvider,
}


def create_providers(
    providers_config: dict[str, ProviderConfig], api_keys: dict[str, dict]
) -> dict[str, MarketDataProvider]:
    result = {
        name: provider_class(provider_config=providers_config[name], api_key=api_keys.get(name))
        for name, provider_class in PROVIDER_REGISTRY.items()
    }
    return result


class FetchController:
    def __init__(
        self,
        series: Iterable[Series],
        get_asset_by_id: Callable[[int], Asset],
        get_provider: Callable[[str], MarketDataProvider],
        **kwargs,
    ):
        self.series_list: Iterable[Series] = series
        self.get_asset_by_id = get_asset_by_id
        self.get_provider = get_provider
        self.now = kwargs.pop("now_provider", now_second_precision)

    def fetch_incrementally(self, state: State) -> Iterable[FetchResult]:

        for series in self.series_list:
            state_entry = state.get_series_state(series.id)
            asset = self.get_asset_by_id(series.asset_id)
            if asset is None:
                yield FetchResult.fail(
                    series.name,
                    f"Could not find asset {series.asset_id} ({series.asset_name})",
                    f"Skipped series '{series.name}'",
                )
                continue
            provider = self.get_provider(asset.provider)
            if not provider:
                yield FetchResult.fail(
                    series.name, f"no provider '{asset.provider}'", f"Skipped series '{series.name}'"
                )
                continue
            range = self.compute_fetch_range(series=series, provider=provider, state=state_entry)
            if range is None:
                continue
            start, end, is_incremental = range
            yield provider.fetch(series, asset, start, end, is_incremental)

    def get_sweep_start(self, state: SeriesState, sweep: SweepConfig, last: datetime):
        if sweep.window <= timedelta(0):
            return None
        if state.next_sweep is not None and state.next_sweep > last:
            return None
        return state.sweep_start

    def update_sweep_state(self, state: SeriesState, sweep: SweepConfig, last: datetime):
        state.next_sweep = last + sweep.cadence
        state.sweep_start = last - sweep.window
        state.needs_save = True

    @staticmethod
    def compute_label_window(
        series: Series, calendar: SeriesCalendar, now: datetime
    ) -> tuple[datetime, datetime] | None:
        horizon = series.bootstrap_history_delta()
        if series.retention_delta() is not None:
            horizon = min(horizon, series.retention_delta())

        first_req = calendar.next_label_time(now - horizon)

        # the last one we need is the last one that could be published
        pub_offset_utc = calendar.publication_delta(now)
        last_req = calendar.previous_label_time(now - pub_offset_utc)
        return first_req, last_req

    @staticmethod
    def compute_prepend_range(
        calendar: SeriesCalendar, state: SeriesState, first_req: datetime
    ) -> tuple[datetime, datetime | None] | None:
        if state.first_point is None:
            return first_req, None  # full history

        last_missing = calendar.last_label_time_before(state.first_point)
        if last_missing >= first_req:
            return first_req, last_missing
        return None

    def compute_fetch_range(
        self, series: Series, provider: MarketDataProvider, state: SeriesState | None
    ) -> tuple[datetime, datetime, bool] | None:
        """
        Unified fetch decision: if fetch needed → return (start, end, is_incremental), else None
        """

        calendar = SeriesCalendar.from_series(series)
        now = self.now()
        first_req, last_req = self.compute_label_window(series, calendar, now)

        # edge case. e.g. when retention horizon lands in a weekend
        if first_req > last_req:
            return None

        sweep = provider.provider_config.get_sweep(series.interval_delta())

        # if we have missing history, grab that first
        # This can mean we skip a daily publication (but that will be picked up next run)
        # we won't do the sweep now either
        prepend_range = self.compute_prepend_range(calendar, state, first_req)
        if prepend_range is not None:
            start, end = prepend_range
            if end is None:
                # Full history update, is also a sweep
                self.update_sweep_state(state, sweep, last_req)
                end = last_req
            return (start, end, False)

        sweep_start = self.get_sweep_start(state, sweep, last_req)
        if sweep_start is not None:
            retention = series.retention_delta()
            if retention is not None:
                sweep_start = max(sweep_start, now - retention)
            first_point = calendar.next_label_time(sweep_start)
            self.update_sweep_state(state, sweep, last_req)
            return (first_point, last_req, False)

        if last_req > state.last_point:
            first_point = state.last_point + series.interval_delta()
            return (first_point, last_req, True)
        return None
