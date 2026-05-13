# Copyright 2026 Rik Essenius
# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.
# File: finance/fetch/controller.py

import time

from finance.common.freshness import is_recent

from .ecb import fetch_ecb
from .fred import fetch_fred_series
from .yahoo import fetch_yahoo_chart


class FetchController:
    def __init__(self, symbols, api_keys, now_provider=time.time):
        self.symbols = symbols
        self.api_keys = api_keys
        self.now = now_provider
        # fetcher registry with correct signatures
        self.fetchers = {
            "yahoo": lambda cfg, api_key: fetch_yahoo_chart(cfg["symbol"]),
            "ecb": lambda cfg, api_key: fetch_ecb(cfg["symbol"]),
            "fred": lambda cfg, api_key: fetch_fred_series(cfg["symbol"], api_key),
        }

    def fetch_one(self, name, cfg, state):
        source_type = cfg.get("source")
        api_key = self.api_keys.get(source_type)

        fetcher = self.fetchers.get(source_type)
        if fetcher is None:
            print(f"Skipping {source_type} metric {name} - no fetcher")
            return None

        now = int(self.now())
        result = fetcher(cfg, api_key)

        value = result.get("value")
        ts = result.get("timestamp")

        entry = state.setdefault(name, {})
        entry["last_try"] = now

        if value is not None and ts is not None:
            return value, ts

        return None

    def fetch_all(self, state):
        now = int(self.now())
        results = {}
        for name, cfg in self.symbols.items():
            interval = cfg["interval"]
            entry = state.get(name, {})
            if is_recent(entry, now, interval):
                continue

            fetched = self.fetch_one(name, cfg, state)
            if fetched is not None:
                results[name] = fetched

        return results
