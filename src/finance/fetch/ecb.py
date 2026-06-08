# Copyright 2026 Rik Essenius
# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.
# File: src/finance/fetch/ecb.py

from datetime import datetime

import requests

from ..common.model import FetchPoint, FetchResult
from .provider import MarketDataProvider

BASE_URL = "https://data-api.ecb.europa.eu/service/data"


class EcbProvider(MarketDataProvider):
    """ECB daily FX provider (no intraday)."""

    def fetch(self, name, asset, last_timestamp) -> FetchResult:
        symbol = asset["symbol"]
        field = asset["fields"][0]
        return self._safe_call(measurement=name, fn=lambda: self._fetch(name, symbol, field), context="fetch")

    def _fetch(self, name, symbol, field) -> FetchResult:
        """
        symbol: e.g. 'USD_EUR'
        returns: [{"timestamp": int, "fields": {field: float}}] or []
        """

        try:
            parts = symbol.split("_")
            if len(parts) != 2:
                raise ValueError
            base, quote = parts
            if not base or not quote:
                raise ValueError
        except Exception:
            return FetchResult.fail(name, f"Could not split symbol '{symbol}' into base_quote")

        series = f"EXR/D.{base}.{quote}.SP00.A"
        url = f"{BASE_URL}/{series}?format=jsondata&lastNObservations=1&detail=dataonly"

        response = requests.get(url, timeout=10)

        response.raise_for_status()

        data = response.json()

        value_result = self._safe_get(data, ["dataSets", 0, "series", "0:0:0:0:0", "observations", "0", 0])

        if not value_result.ok:
            return FetchResult.fail(name, f"Could not interpret path for {field}", value_result.reason)

        value = value_result.payload
        timestamp_result = self._safe_get(data, ["structure", "dimensions", "observation", 0, "values", 0, "start"])

        if not timestamp_result.ok:
            return FetchResult.fail(name, "Could not interpret path for timestamp", timestamp_result.reason)

        timestamp = int(datetime.fromisoformat(timestamp_result.payload).timestamp())

        return FetchResult.ok_payload(name, [FetchPoint(timestamp=timestamp, fields={field: value})])
