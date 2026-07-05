# Copyright 2026 Rik Essenius
# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.
# File: src/finance/fetch/controller.py

from collections.abc import Callable, Iterable
from datetime import UTC, datetime, timedelta

from finance.common.time_utils import parse_duration
from finance.fetch.provider import MarketDataProvider

from ..common.model import Asset, FetchResult, ProviderConfig, Series, SupportedProviders
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

    def get_window(
        self, first_saved: datetime | None, last_saved: datetime | None, limit: timedelta
    ) -> tuple[datetime, datetime]:

        now = self.now()
        window_start = now - limit

        # Case 1: no history yet, get maximum
        if first_saved is None or last_saved is None:
            return window_start, now

        # Case 2: history needed before first saved point (so get maximum and let the ingestion eliminate duplicates)
        if first_saved > window_start:
            return window_start, now

        # Case 3: user waited too long → last_saved is outside the allowed window
        if last_saved < window_start:
            return window_start, now

        # Case 4: normal incremental fetch → fetch after last_saved
        return last_saved, now

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
            entry = state.get(series.id)
            first_saved = None if entry is None else entry.first_time
            last_saved = None if entry is None else entry.last_time
            provider_limit = provider.provider_config.get_history_limit(series.interval)
            limit = series.bootstrap_history_delta()

            if provider_limit is not None:
                limit = min(limit, provider_limit)
            start, end = self.get_window(first_saved, last_saved, limit)

            result: FetchResult = provider.fetch(series, asset, start, end)

        # TODO eliminate. Don't think we need it right now
        state.update_after_fetch(series.id, self.now())
        return result

    def fetch_incrementally(self, state: State) -> Iterable[FetchResult]:
        now = self.now()

        for series in self.series_list:
            # Freshness check
            state_entry = state.get(series.id)
            fresh = state_entry is not None and now - state_entry.last_time < series.interval_delta()
            if fresh:
                # not an error, just skip
                continue

            # Fetch
            yield self.fetch_one_series(series, state)
