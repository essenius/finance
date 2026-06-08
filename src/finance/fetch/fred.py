# Copyright 2026 Rik Essenius
# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.
# File: src/finance/fetch/fred.py

from datetime import UTC, datetime

import requests

from ..common.model import FetchPoint, FetchResult
from .provider import MarketDataProvider

BASE_URL = "https://api.stlouisfed.org/fred/series/observations"


class FredProvider(MarketDataProvider):
    """FRED daily economic data provider."""

    def fetch(self, name, asset, last_timestamp) -> FetchResult:
        symbol = asset["symbol"]
        field = asset["fields"][0]

        api_key = self.config.get("api_key")
        if not api_key:
            return FetchResult.fail(name, "FRED requires an API key")

        return self._safe_call(measurement=name, fn=lambda: self._fetch(name, symbol, field, api_key), context="fetch")

    def _fetch(self, name, symbol, field, api_key) -> FetchResult:
        params = {
            "series_id": symbol,
            "api_key": api_key,
            "file_type": "json",
            "sort_order": "desc",
            "limit": 1,
        }

        response = requests.get(BASE_URL, params=params, timeout=10)
        response.raise_for_status()

        data = response.json()
        observations = data.get("observations", [])
        if not observations:
            return FetchResult.fail(name, "no 'observations' in response")

        obs = observations[0]
        value_str = obs.get("value")
        date_str = obs.get("date")

        if value_str in (None, ".", ""):
            return FetchResult.fail(name, f"invalid value '{value_str}' in first observation")

        value = float(value_str)
        timestamp = int(datetime.fromisoformat(date_str).replace(tzinfo=UTC).timestamp())

        return FetchResult.ok_payload(name, [FetchPoint(timestamp=timestamp, fields={field: value})])
