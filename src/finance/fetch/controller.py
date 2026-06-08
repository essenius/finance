# Copyright 2026 Rik Essenius
# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.
# File: src/finance/fetch/controller.py

import time
from collections.abc import Iterable

from ..common.freshness import is_recent
from ..common.intervals import parse_interval
from ..common.model import FetchResult
from ..state.manager import State
from .ecb import EcbProvider
from .fred import FredProvider
from .yahoo import YahooProvider

PROVIDER_REGISTRY = {
    "yahoo": YahooProvider,
    "fred": FredProvider,
    "ecb": EcbProvider,
}


class FetchController:
    def __init__(self, assets: dict, api_keys: dict | None = None, now_provider=time.time):
        self.assets = assets
        self.api_keys = api_keys or {}
        self.now = now_provider

        # Instantiate all providers with their API key (or None)
        self.providers = {
            name: provider_class(self.api_keys.get(name)) for name, provider_class in PROVIDER_REGISTRY.items()
        }

    def fetch_one_series(self, name: str, asset: dict, state: State) -> FetchResult:

        provider = self.providers.get(asset["provider"])
        if provider is None:
            result = FetchResult.fail(name, f"no provider '{asset['provider']}'", f"Skipped series {name}")
        else:
            last_timestamp = state.get(name, {}).get("last_timestamp")
            result = provider.fetch(name, asset, last_timestamp)

        state.update_after_fetch(result)
        return result

    def fetch_incrementally(self, state: State) -> Iterable[FetchResult]:
        now = int(self.now())

        for name, asset in self.assets.items():
            # Freshness check
            try:
                interval_s = parse_interval(asset["interval"])
            except ValueError as ve:
                result = FetchResult.fail(name, f"could not parse interval '{asset['interval']}'", ve)
                state.update_after_fetch(result)
                yield result
                continue
            state_entry = state.get(name)
            if is_recent(state_entry, now, interval_s):
                # not an error, just skip
                continue

            # Fetch
            yield self.fetch_one_series(name, asset, state)
