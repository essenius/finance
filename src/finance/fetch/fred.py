# Copyright 2026 Rik Essenius
# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.
# File: src/finance/fetch/fred.py

from datetime import UTC, datetime

import requests

from .provider import MarketDataProvider

BASE_URL = "https://api.stlouisfed.org/fred/series/observations"


class FredProvider(MarketDataProvider):
    """FRED daily economic data provider."""

    def fetch(self, asset, last_timestamp):
        symbol = asset["symbol"]
        field = asset["fields"][0]

        api_key = self._require_api_key(symbol)
        if api_key is None:
            return []

        return self._safe(symbol, lambda: self._fetch(symbol, field, api_key))

    def _fetch(self, symbol, field, api_key):
        params = {
            "series_id": symbol,
            "api_key": api_key,
            "file_type": "json",
            "sort_order": "desc",
            "limit": 1,
        }

        response = requests.get(BASE_URL, params=params, timeout=10)
        if not self._check_status(symbol, response):
            return []

        data = response.json()
        observations = data.get("observations", [])
        if not observations:
            self.error("no 'observations' in response", symbol)
            return []

        obs = observations[0]
        value_str = obs.get("value")
        date_str = obs.get("date")

        if value_str in (None, ".", ""):
            self.error(f"invalid value '{value_str}' in first observation", symbol)
            return []

        value = float(value_str)
        timestamp = int(datetime.fromisoformat(date_str).replace(tzinfo=UTC).timestamp())

        return [{"timestamp": timestamp, "fields": {field: value}}]
