# Copyright 2026 Rik Essenius
# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.
# File: src/finance/fetch/controller.py

import time

from finance.common.freshness import is_recent
from finance.common.intervals import parse_interval
from finance.common.log_mixin import LogMixin
from finance.fetch.ecb import EcbProvider
from finance.fetch.fred import FredProvider
from finance.fetch.yahoo import YahooProvider

PROVIDER_REGISTRY = {
    "yahoo": YahooProvider,
    "fred": FredProvider,
    "ecb": EcbProvider,
}


class FetchController(LogMixin):
    def __init__(self, assets, api_keys, now_provider=time.time):
        self.assets = assets
        self.api_keys = api_keys
        self.now = now_provider

        # Instantiate all providers with their API key (or None)
        self.providers = {
            name: provider_class(api_keys.get(name)) for name, provider_class in PROVIDER_REGISTRY.items()
        }

    def _validate_result(self, result):
        if not isinstance(result, dict):
            return None

        timestamp = result.get("timestamp")
        fields = result.get("fields")

        if not isinstance(timestamp, int):
            return None

        if not isinstance(fields, dict):
            return None

        return result

    def fetch_one(self, name, asset, state: dict):

        provider = self.providers.get(asset["provider"])
        if provider is None:
            self.error(f"Skipping {asset['provider']} series {name} - no provider")
            return None

        now = int(self.now())

        last_timestamp = state.get(name, {}).get("last_timestamp")

        try:
            result = provider.fetch(asset, last_timestamp)

        except Exception as ex:
            self.error(f"Fetcher for {name} failed: {ex}")
            entry = state.setdefault(name, {})
            entry["last_try"] = now
            return None

        validated = self._validate_result(result)
        entry = state.setdefault(name, {})
        entry["last_try"] = now

        if validated is None:
            return None

        timestamp = validated["timestamp"]
        fields = validated["fields"]
        entry["last_timestamp"] = timestamp
        return {"timestamp": timestamp, "fields": fields}

    def fetch_all(self, state: dict):
        now = int(self.now())
        results = {}

        for name, asset in self.assets.items():
            required = ["asset", "provider", "symbol", "interval", "fields", "timeseries"]
            missing = [k for k in required if k not in asset]
            if missing:
                self.error(f"Asset {name} missing keys: {missing}")
                continue

            interval_s = parse_interval(asset["interval"])

            entry = state.get(name, {})
            if is_recent(entry, now, interval_s):
                continue

            fetched = self.fetch_one(name, asset, state)

            if fetched is not None:
                results[name] = fetched

        return results
