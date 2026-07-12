# Copyright 2026 Rik Essenius
# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.
# File: src/finance/fetch/controller.py

from collections.abc import Callable, Iterable
from datetime import UTC, datetime, timedelta

from finance.fetch.provider import MarketDataProvider

from ..common.model import Asset, CompletionPolicy, FetchResult, ProviderConfig, Series, SeriesState, SupportedProviders
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
        self.now = kwargs.pop("now_provider", lambda: datetime.now(UTC))

    '''
    TODO delete
    def get_window(
        self, first_saved: datetime | None, last_saved: datetime | None, limit: timedelta, overlap: timedelta
    ) -> tuple[datetime, datetime, bool]:  # start of window, end of window

        is_incremental = True
        now = self.now()
        window_start = now - limit

        # No history yet, get maximum
        if first_saved is None or last_saved is None:
            return window_start, now, not is_incremental

        # History needed before first saved point (so get maximum and let the ingestion handle duplicates)
        if first_saved > window_start:
            return window_start, now, not is_incremental

        start_point = last_saved - overlap
        # Start point is too far in the past, so limit to the allowed window
        if start_point < window_start:
            return window_start, now, not is_incremental

        # Normal incremental fetch → fetch after last_saved - overlap
        return start_point, now, is_incremental
            '''

    def fetch_one_series(self, series: Series, state: State) -> FetchResult:

        asset = self.get_asset_by_id(series.asset_id)
        if asset is None:
            return FetchResult.fail(
                series.name,
                f"Could not find asset {series.asset_id} ({series.asset_name})",
                f"Skipped series '{series.name}'",
            )

        provider = self.get_provider(asset.provider)
        if provider is None:
            result = FetchResult.fail(series.name, f"no provider '{asset.provider}'", f"Skipped series '{series.name}'")
        else:
            entry = state.get_series_state(series.id)
            interval = series.interval_delta()
            config = provider.provider_config
            provider_limit = config.get_history_limit(interval)
            overlap = config.get_overlap(interval)
            limit = series.bootstrap_history_delta()
            if provider_limit is not None:
                limit = min(limit, provider_limit)
            now = self.now()
            start, is_incremental = entry.set_window(now, limit, overlap)
            result: FetchResult = provider.fetch(series, asset, start, now, is_incremental)

        return result

    def fetch_incrementally(self, state: State) -> Iterable[FetchResult]:

        for series in self.series_list:
            # Freshness check
            state_entry = state.get_series_state(series.id)
            if self.should_fetch(series, state_entry):
                yield self.fetch_one_series(series, state)

    def should_fetch(self, series: Series, state_entry: SeriesState | None) -> bool:
        # Nothing fetched yet
        if state_entry.last_point is None:
            return True

        now = self.now()
        # We don't have sufficient history
        if state_entry.first_point > now - series.bootstrap_history_delta():
            return True

        # if the interval after the last fetched point is not closed yet, don't fetch
        interval_closed = (now - state_entry.last_point) >= series.interval_delta()
        if not interval_closed:
            return False

        # the interval is closed and the policy is interval close
        if series.completion_policy == CompletionPolicy.INTERVAL_CLOSE:
            return True

        # we have a NEXT_DAY completion policy. Only fetch if the day passed.
        today = now.date()
        return state_entry.last_point.date() < today - timedelta(days=1)
