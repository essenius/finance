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
            "yahoo": lambda cfg, api_keys: fetch_yahoo_chart(cfg["symbol"]),
            "ecb":   lambda cfg, api_keys: fetch_ecb(cfg["symbol"]),
            "fred":  lambda cfg, api_keys: fetch_fred_series(cfg["symbol"], api_keys),
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
        print(f"FetchController: now={now}, state={state}")  # Debug print
        results = {}
        print(f"symbols: {self.symbols}")  # Debug print
        for name, cfg in self.symbols.items():
            interval = cfg["interval"]
            entry = state.get(name, {})
            print(f"Checking {name}: last_try={entry.get('last_try')}, last_value={entry.get('last_value')}, last_timestamp={entry.get('last_timestamp')}")  # Debug print
            if is_recent(entry, now, interval):
                print(f"Skipping {name} - last try was {now - entry.get('last_try', 0)} seconds ago")  # Debug print
                continue

            fetched = self.fetch_one(name, cfg, state)
            if fetched is not None:
                results[name] = fetched

        return results
