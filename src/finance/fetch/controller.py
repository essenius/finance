# Copyright 2026 Rik Essenius
# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.
# File: src/finance/fetch/controller.py

from collections.abc import Iterable
from datetime import UTC, datetime

from finance.fetch.provider import MarketDataProvider

from ..common.freshness import is_recent
from ..common.model import FetchResult
from ..state.state import State
from .ecb import EcbProvider
from .fred import FredProvider
from .yahoo import YahooProvider

# make sure this aligns with PROVIDERS in config/loader.py
PROVIDER_REGISTRY = {
    "yahoo": YahooProvider,
    "fred": FredProvider,
    "ecb": EcbProvider,
}


def create_providers(providers_config: dict[str, dict], api_keys: dict[str, dict]) -> dict[str, MarketDataProvider]:
    return {
        name: provider_class(provider_config=providers_config[name], api_key=api_keys.get(name))
        for name, provider_class in PROVIDER_REGISTRY.items()
    }


class FetchController:
    def __init__(self, assets: dict, providers: dict, **kwargs):
        self.assets = assets
        self.providers = providers
        self.now = kwargs.pop("now_provider", lambda: datetime.now(UTC))

    def get_window(self, first_saved: int | None, last_saved: int | None, limit: int) -> tuple[int, int]:

        now_timestamp = self.now().timestamp()
        window_start = now_timestamp - limit

        # Case 1: no history yet, get maximum
        if first_saved is None or last_saved is None:
            return window_start, now_timestamp

        # Case 2: history needed before first saved point (so get maximum and let the ingestion eliminate duplicates)
        if first_saved > window_start:
            return window_start, now_timestamp

        # Case 3: user waited too long → last_saved is outside the allowed window
        if last_saved < window_start:
            return window_start, now_timestamp

        # Case 4: normal incremental fetch → fetch after last_saved
        return last_saved, now_timestamp

    def fetch_one_series(self, name: str, asset: dict, state: State) -> FetchResult:

        provider = self.providers.get(asset["provider"])
        if provider is None:
            result = FetchResult.fail(name, f"no provider '{asset['provider']}'", f"Skipped series {name}")
        else:
            entry = state.get(name, {})
            first_saved = entry.get("first_timestamp")
            last_saved = entry.get("last_timestamp")
            limit = asset["history_limit_seconds"]
            start, end = self.get_window(first_saved, last_saved, limit)
            result = provider.fetch(name, asset, start, end)

        state.update_after_fetch(result, self.now().timestamp())
        return result

    def fetch_incrementally(self, state: State) -> Iterable[FetchResult]:
        now_timestamp = int(self.now().timestamp())

        for name, asset in self.assets.items():
            # Freshness check
            interval_s = asset["interval_seconds"]
            state_entry = state.get(name)
            if is_recent(state_entry, now_timestamp, interval_s):
                # not an error, just skip
                continue

            # Fetch
            yield self.fetch_one_series(name, asset, state)
